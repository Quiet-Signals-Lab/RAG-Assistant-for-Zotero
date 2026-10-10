import React, { useState } from 'react';
import { useProfile } from '../../contexts/ProfileContext';
import Button from '../ui/Button';

interface ProfileSelectorProps {
  className?: string;
}

const ProfileSelector: React.FC<ProfileSelectorProps> = ({ className = '' }) => {
  const {
    profiles,
    activeProfileId,
    activeProfile,
    isLoading,
    switchProfile,
    createProfile,
    deleteProfile
  } = useProfile();

  const [isCreating, setIsCreating] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleSwitchProfile = async (profileId: string) => {
    if (profileId === activeProfileId) return;
    
    const confirmed = window.confirm(
      'Switching profiles will reload the application. Any unsaved changes will be lost. Continue?'
    );
    
    if (confirmed) {
      await switchProfile(profileId);
    }
  };

  const handleDeleteProfile = async () => {
    if (!activeProfileId || !activeProfile) return;
    
    if (profiles.length <= 1) {
      alert('Cannot delete the last profile. At least one profile must exist.');
      return;
    }
    
    const confirmed = window.confirm(
      `Are you sure you want to delete the profile "${activeProfile.name}"? This will delete all associated data including chat sessions and vector database. This action cannot be undone.`
    );
    
    if (!confirmed) return;
    
    const confirmAgain = window.confirm(
      'This is your last warning. All data in this profile will be permanently deleted. Are you absolutely sure?'
    );
    
    if (!confirmAgain) return;
    
    setIsDeleting(true);
    
    try {
      const success = await deleteProfile(activeProfileId, true);
      if (success) {
        // Profile deletion will trigger app reload, so no need for additional actions
        alert('Profile deleted successfully. The application will now reload.');
      } else {
        alert('Failed to delete profile. Please try again.');
      }
    } catch (error) {
      console.error('Error deleting profile:', error);
      alert('An error occurred while deleting the profile.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCreateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!newProfileName.trim()) return;
    
    setIsCreating(true);
    
    // Generate ID from name (lowercase, replace spaces with hyphens)
    const profileId = newProfileName.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    
    const profile = await createProfile(profileId, newProfileName);
    
    if (profile) {
      setNewProfileName('');
      setShowCreateForm(false);
    }
    
    setIsCreating(false);
  };

  if (isLoading) {
    return (
      <div className={`profile-selector ${className}`}>
        <span className="text-muted">Loading profiles…</span>
      </div>
    );
  }

  return (
    <div className={`profile-selector ${className}`}>
      <div className="profile-selector-header">
        <label htmlFor="profile-select" className="profile-label">
          Profile
        </label>
        <select
          id="profile-select"
          value={activeProfileId || ''}
          onChange={(e) => handleSwitchProfile(e.target.value)}
          className="profile-select"
          disabled={profiles.length === 0}
        >
          {profiles.length === 0 && (
            <option value="">No profiles</option>
          )}
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.name}
            </option>
          ))}
        </select>
        <Button
          onClick={() => setShowCreateForm(!showCreateForm)}
          variant="secondary"
        >
          {showCreateForm ? 'Cancel' : 'New profile'}
        </Button>
        {profiles.length > 1 && activeProfileId && (
          <Button
            onClick={handleDeleteProfile}
            variant="secondary"
            className="btn--danger"
            disabled={isDeleting}
            title="Delete current profile"
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </Button>
        )}
      </div>

      {showCreateForm && (
        <form onSubmit={handleCreateProfile} className="profile-create-form">
          <input
            type="text"
            value={newProfileName}
            onChange={(e) => setNewProfileName(e.target.value)}
            placeholder="Profile name"
            className="profile-input"
            disabled={isCreating}
            autoFocus
          />
          <Button
            type="submit"
            disabled={isCreating || !newProfileName.trim()}
            >
            {isCreating ? 'Creating...' : 'Create'}
          </Button>
        </form>
      )}

      {activeProfile && (
        <div className="profile-info">
          <small className="text-muted">
            {activeProfile.description || 'Active profile'}
          </small>
        </div>
      )}

    </div>
  );
};

export default ProfileSelector;
