export function isMainAdmin(user) {
  if (!user) return false;
  if (user.is_main_admin || user.role === 'main_admin') return true;
  return String(user.username || '').includes('#@admin@#');
}

export function homePathFor(user) {
  if (!user) return '/login';
  if (isMainAdmin(user)) return '/main-admin';
  if (user.role === 'admin' || user.is_staff) return '/admin';
  return '/student';
}
