import { friendlyUserMessage } from '../../api';

/**
 * Shows a calm banner. Error variant is always scrubbed of technical / stack text.
 */
export default function Alert({ children, variant = 'error' }) {
  if (children == null || children === false || children === '') return null;

  let content = children;
  if (variant === 'error') {
    if (typeof children === 'string' || typeof children === 'number' || children instanceof Error) {
      content = friendlyUserMessage(children, 'Something went wrong. Please try again.');
    }
  }

  return <div className={`alert${variant === 'info' ? ' info' : ''}`}>{content}</div>;
}
