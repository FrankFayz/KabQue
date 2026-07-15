/** True only for KabQue Main Admin accounts. */
export function isMainAdmin(user) {
  if (!user) return false;
  if (user.is_main_admin || user.role === 'main_admin') return true;
  return String(user.username || '').includes('#@admin@#');
}

/**
 * Desk supervisor (approved Kabale staff). Never Main Admin, never student.
 * Do not use is_staff alone — that can wrongly elevate accounts.
 */
export function isSupervisor(user) {
  if (!user || isMainAdmin(user)) return false;
  if (user.role !== 'admin') return false;
  if (user.is_approved === false) return false;
  return true;
}

/** Fresher accounts only. */
export function isStudent(user) {
  if (!user || isMainAdmin(user)) return false;
  return user.role === 'student';
}

/** Home path after login — each role stays in its own area. */
export function homePathFor(user) {
  if (!user) return '/login';
  if (isMainAdmin(user)) return '/main-admin';
  if (isSupervisor(user)) return '/admin';
  if (user.role === 'admin') return '/login'; // supervisor waiting approval / unverified
  return '/student';
}
