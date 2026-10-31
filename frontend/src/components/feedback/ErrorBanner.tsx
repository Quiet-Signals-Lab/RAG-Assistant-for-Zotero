import React from "react";

interface Props {
  message: string;
  onDismiss?: () => void;
}

const ErrorBanner: React.FC<Props> = ({ message, onDismiss }) => {
  if (!message) return null;
  return (
    <div className="error-banner">
      {message}
      {onDismiss && <>{" "}<button type="button" className="link-button" onClick={onDismiss}>Dismiss</button></>}
    </div>
  );
};

export default ErrorBanner;
