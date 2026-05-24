/* Sensor — retro control-panel toggle for a data source. */

function Sensor({ ic, name, label, on, onToggle }) {
  return (
    <div
      className={`sensor-card${on ? ' active' : ''}`}
      onClick={onToggle}
      title={on ? `${label} — connected. Click to dim.` : `${label} — dormant. Click to activate (demo).`}
    >
      <div className="sensor-icon">{ic}</div>
      <div className="sensor-name">{name}</div>
      <div className="sensor-label">{label}</div>
      <div className={`sensor-status ${on ? 'on' : 'off'}`}>
        {on ? '● CONNECTED' : '○ DORMANT'}
      </div>
    </div>
  );
}

Object.assign(window, { Sensor });
