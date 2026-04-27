'use server';

import { createSession, deleteSession } from './session';
import { redirect } from 'next/navigation';

// Admin credentials from environment or defaults for dev
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@dario.ai';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'dario2026';
const DEMO_ENABLED = process.env.DEMO_MODE !== 'false';

export async function login(prevState: any, formData: FormData) {
  const email = formData.get('email') as string;
  const password = formData.get('password') as string;

  if (!email || !password) {
    return { error: 'Email and password are required.' };
  }

  // Admin login
  if (email === ADMIN_EMAIL && password === ADMIN_PASSWORD) {
    await createSession({
      id: 'admin-1',
      name: 'DARIO Admin',
      email: ADMIN_EMAIL,
      role: 'admin',
    });
    redirect('/command-center');
  }

  return { error: 'Invalid credentials.' };
}

export async function loginAsDemo() {
  if (!DEMO_ENABLED) {
    return { error: 'Demo mode is disabled.' };
  }

  await createSession({
    id: 'demo-1',
    name: 'Demo User',
    email: 'demo@dario.ai',
    role: 'demo',
  });
  redirect('/command-center');
}

export async function logout() {
  await deleteSession();
  redirect('/login');
}
