/* StatCard — chunky retro gauge with bottom-border accent. */

function StatCard({ label, value, tone = 'gray' }) {
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-num">{value}</div>
    </div>
  );
}

Object.assign(window, { StatCard });
