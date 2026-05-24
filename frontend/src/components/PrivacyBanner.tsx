import { IconLock } from "@/components/icons";

export function PrivacyBanner() {
  return (
    <div className="privacy-banner">
      <span className="privacy-icon" aria-hidden="true">
        <IconLock size={18} />
      </span>
      <div className="privacy-text">
        <strong>Your data never leaves this device.</strong>{" "}
        All processing happens locally — no cloud, no servers. Powered by a
        local AI model.
      </div>
    </div>
  );
}
