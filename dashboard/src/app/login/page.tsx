'use client';

import { login, loginAsDemo } from '@/lib/auth';
import { useActionState } from 'react';

export default function LoginPage() {
  const [state, formAction, pending] = useActionState(login, null);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0e1a]">
      <div className="w-full max-w-md space-y-8">
        {/* Logo */}
        <div className="text-center">
          <h1 className="text-4xl font-extrabold tracking-tight text-white">
            D<span className="text-[#00e5ff]">.</span>A
            <span className="text-[#00e5ff]">.</span>R
            <span className="text-[#00e5ff]">.</span>I
            <span className="text-[#00e5ff]">.</span>O
          </h1>
          <p className="mt-2 text-sm text-gray-400">AI Orchestrator Framework</p>
          <p className="mt-1 text-xs text-gray-500">Sign in to access your command center</p>
        </div>

        {/* Login form */}
        <form action={formAction} className="bg-[#111827] border border-[#2a3a5a] rounded-2xl p-8 space-y-6">
          {state?.error && (
            <div className="rounded-lg bg-red-400/10 border border-red-400/20 px-4 py-3 text-sm text-red-400">
              {state.error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              required
              className="w-full rounded-lg border border-[#2a3a5a] bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-[#00e5ff] focus:outline-none focus:ring-1 focus:ring-[#00e5ff] transition-colors"
              placeholder="admin@dario.ai"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              required
              className="w-full rounded-lg border border-[#2a3a5a] bg-[#0a0e1a] px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-[#00e5ff] focus:outline-none focus:ring-1 focus:ring-[#00e5ff] transition-colors"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-lg bg-[#00e5ff] px-4 py-3 text-sm font-bold text-[#0a0e1a] hover:bg-[#00e5ff]/90 focus:outline-none focus:ring-2 focus:ring-[#00e5ff] focus:ring-offset-2 focus:ring-offset-[#0a0e1a] transition-colors disabled:opacity-50"
          >
            {pending ? 'Signing in...' : 'Sign In'}
          </button>

        </form>

        <div className="bg-[#111827] border border-[#2a3a5a] rounded-2xl px-8 py-4">
          <div className="relative mb-4">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-[#2a3a5a]" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-[#111827] px-3 text-gray-500">or</span></div>
          </div>

          <form action={loginAsDemo as any}>
            <button
              type="submit"
              className="w-full rounded-lg border border-[#2a3a5a] bg-transparent px-4 py-3 text-sm font-medium text-gray-300 hover:border-[#00e5ff]/40 hover:bg-[#00e5ff]/5 focus:outline-none transition-colors"
            >
              Try Demo Mode
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-600">
          Powered by DARIO Orchestrator Framework v1.6
        </p>
      </div>
    </div>
  );
}
