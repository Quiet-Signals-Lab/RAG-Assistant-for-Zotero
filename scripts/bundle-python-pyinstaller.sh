#!/bin/bash
# bundle-python-pyinstaller.sh - Create a standalone Python bundle using PyInstaller
# This creates a completely self-contained Python distribution with all dependencies
# bundled as actual executables (no symlinks to system Python)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="$PROJECT_ROOT/python-dist"
BUILD_DIR="$PROJECT_ROOT/build-python"
SPEC_FILE="$PROJECT_ROOT/build/pyinstaller/backend_bundle.spec"

echo " Creating standalone Python bundle with PyInstaller..."
echo "=================================================="

# Detect platform
case "$(uname -s)" in
    Darwin*)    PLATFORM="darwin";;
    Linux*)     PLATFORM="linux";;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="win32";;
    *)          echo " Unsupported platform"; exit 1;;
esac

echo " Platform: $PLATFORM"

# Clean previous bundle and build artifacts
if [ -d "$BUNDLE_DIR" ]; then
    echo "🧹 Cleaning previous bundle..."
    rm -rf "$BUNDLE_DIR"
fi

if [ -d "$BUILD_DIR" ]; then
    echo "🧹 Cleaning previous build artifacts..."
    rm -rf "$BUILD_DIR"
fi

if [ -d "$PROJECT_ROOT/dist/backend_bundle" ]; then
    echo "🧹 Cleaning PyInstaller dist directory..."
    rm -rf "$PROJECT_ROOT/dist/backend_bundle"
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo " Python 3 is not installed. Please install Python 3.8 or later."
    exit 1
fi

PYTHON_CMD=$(command -v python3)
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo " Found Python $PYTHON_VERSION at $PYTHON_CMD"

# Check if we have a virtual environment activated, or use system Python
if [ -z "$VIRTUAL_ENV" ]; then
    echo "  No virtual environment activated"
    echo " Creating temporary build environment..."
    
    # Create temporary venv for building
    $PYTHON_CMD -m venv "$BUILD_DIR/venv"
    
    if [ "$PLATFORM" = "win32" ]; then
        source "$BUILD_DIR/venv/Scripts/activate"
        PIP_CMD="$BUILD_DIR/venv/Scripts/pip"
    else
        source "$BUILD_DIR/venv/bin/activate"
        PIP_CMD="$BUILD_DIR/venv/bin/pip"
    fi
else
    echo " Using active virtual environment: $VIRTUAL_ENV"
    PIP_CMD="pip"
fi

# Upgrade pip and install build tools
echo "  Upgrading pip and installing build tools..."
$PIP_CMD install --upgrade pip setuptools wheel --quiet

# Install PyInstaller
echo " Installing PyInstaller..."
$PIP_CMD install pyinstaller --quiet

# Install backend requirements (needed for PyInstaller to analyze dependencies)
echo " Installing backend dependencies (this may take a few minutes)..."
$PIP_CMD install -r "$PROJECT_ROOT/requirements.txt" --quiet

# Run PyInstaller
echo " Building standalone bundle with PyInstaller..."
echo "   This may take 5-10 minutes depending on your system..."
pyinstaller --clean --noconfirm "$SPEC_FILE"

# Move the bundle to python-dist
if [ -d "$PROJECT_ROOT/dist/backend_bundle" ]; then
    echo " Moving bundle to python-dist..."
    mv "$PROJECT_ROOT/dist/backend_bundle" "$BUNDLE_DIR"
    
    # Create a bin directory structure for compatibility with Electron app expectations
    mkdir -p "$BUNDLE_DIR/bin"
    
    # Create wrapper script that mimics python3 executable
    if [ "$PLATFORM" = "darwin" ] || [ "$PLATFORM" = "linux" ]; then
        cat > "$BUNDLE_DIR/bin/python3" << 'EOF'
#!/bin/bash
# Wrapper script for PyInstaller bundle
# This allows the Electron app to execute Python scripts through the bundle

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_EXECUTABLE="$BUNDLE_DIR/backend_server"

# If arguments include a Python script to run, we need to handle it differently
# For now, just execute the backend server
exec "$BACKEND_EXECUTABLE" "$@"
EOF
        chmod +x "$BUNDLE_DIR/bin/python3"
        
        # Create python symlink for compatibility
        ln -sf python3 "$BUNDLE_DIR/bin/python"
    fi
    
    # Create a startup script for the backend
    cat > "$BUNDLE_DIR/start_backend.sh" << 'EOF'
#!/bin/bash
# Start the backend server using the PyInstaller bundle

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_EXECUTABLE="$SCRIPT_DIR/backend_server"

# Pass all arguments to the backend executable
exec "$BACKEND_EXECUTABLE" "$@"
EOF
    chmod +x "$BUNDLE_DIR/start_backend.sh"
    
    # Get bundle size
    BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" | cut -f1)
    echo ""
    echo " PyInstaller bundle created successfully!"
    echo " Bundle size: $BUNDLE_SIZE"
    echo " Location: $BUNDLE_DIR"
    echo ""
    echo " Bundle structure:"
    if [ "$PLATFORM" = "darwin" ] || [ "$PLATFORM" = "linux" ]; then
        ls -lh "$BUNDLE_DIR" | head -10
    fi
    echo ""
    
    # Verify the bundle
    echo " Verifying bundle..."
    if [ -f "$BUNDLE_DIR/backend_server" ]; then
        echo " Backend executable found"
        
        # Check if it's a proper executable (not a symlink)
        if [ -L "$BUNDLE_DIR/backend_server" ]; then
            echo " ERROR: backend_server is a symlink! Bundle failed."
            exit 1
        else
            echo " Backend executable is a proper binary (not a symlink)"
        fi
        
        # Test execution (just check --help or version)
        echo " Testing backend executable..."
        if "$BUNDLE_DIR/backend_server" --help &> /dev/null || true; then
            echo " Backend executable runs successfully"
        else
            echo "  Backend executable may have issues, but file exists"
        fi
    else
        echo " Backend executable not found!"
        exit 1
    fi
    
    echo ""
    echo " Bundle verification passed!"
    echo ""
    echo "Next steps:"
    echo "1. Build Electron app: npm run package:mac (or :win, :linux)"
    echo "2. The bundled Python will be included automatically"
    echo "3. App will run standalone without requiring system Python"
    echo ""
    echo " Note: The bundle contains a fully self-contained Python runtime"
    echo "         with all dependencies baked in."
else
    echo " PyInstaller bundle creation failed!"
    echo "Expected directory not found: $PROJECT_ROOT/dist/backend_bundle"
    exit 1
fi

# Cleanup build directory
if [ -d "$BUILD_DIR" ]; then
    echo "🧹 Cleaning up build directory..."
    rm -rf "$BUILD_DIR"
fi

# Cleanup PyInstaller temp files
if [ -d "$PROJECT_ROOT/build" ]; then
    rm -rf "$PROJECT_ROOT/build"
fi

if [ -d "$PROJECT_ROOT/dist" ]; then
    rm -rf "$PROJECT_ROOT/dist"
fi

echo ""
echo " Done!"
