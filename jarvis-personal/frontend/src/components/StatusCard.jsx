export default function StatusCard({ title, value, subtitle }) {
  return (
    <div className="status-card">
      <p>{title}</p>
      <h3>{value}</h3>
      <span>{subtitle}</span>
    </div>
  );
}