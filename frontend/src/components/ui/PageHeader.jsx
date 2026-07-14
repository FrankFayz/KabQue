export default function PageHeader({ eyebrow, title, action }) {
  return (
    <header className="dash-head">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
      </div>
      {action}
    </header>
  );
}
