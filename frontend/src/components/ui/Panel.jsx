export default function Panel({ title, children, wide = false, className = '' }) {
  return (
    <div className={`panel${wide ? ' wide' : ''}${className ? ` ${className}` : ''}`}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </div>
  );
}
