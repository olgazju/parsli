/* Banners — privacy and pending-OAuth */

function PrivacyBanner() {
  return (
    <div className="privacy-banner">
      <div className="privacy-icon">🔒</div>
      <div className="privacy-text">
        <strong>Your data never leaves this device.</strong>{' '}
        All processing happens locally — no cloud, no servers.
        Powered by a local AI model.
      </div>
    </div>
  );
}

function PendingRow({ message }) {
  return (
    <div className="pending-row">
      <Spinner />
      {message}
    </div>
  );
}

Object.assign(window, { PrivacyBanner, PendingRow });
