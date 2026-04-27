#!/usr/bin/env node

/**
 * Orchestrator AI — Dashboard Launcher
 *
 * Usage:
 *   orch-dashboard              Start the dashboard (install deps if needed)
 *   orch-dashboard --port 3001  Start on custom port
 *   orch-dashboard --build      Build for production
 *   orch-dashboard --setup      Install/reinstall dependencies
 */

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const ORCH_DIR = path.join(HOME, '.claude', 'orchestrator');
const DASHBOARD_SRC = path.resolve(__dirname, '..', 'dashboard');
const DASHBOARD_DIR = path.join(ORCH_DIR, 'dashboard');

function log(msg) { console.log(`  \x1b[36m>\x1b[0m ${msg}`); }
function success(msg) { console.log(`  \x1b[32m✓\x1b[0m ${msg}`); }
function error(msg) { console.error(`  \x1b[31m✗\x1b[0m ${msg}`); }

function setupDashboard() {
  log('Setting up dashboard...');

  // Copy dashboard source if not present or outdated
  if (!fs.existsSync(DASHBOARD_DIR)) {
    log('Copying dashboard source...');
    copyDir(DASHBOARD_SRC, DASHBOARD_DIR);
    success('Dashboard source copied');
  }

  // Apply white-label branding from company.yaml
  applyBranding();

  // Install dependencies
  log('Installing dependencies (this may take a moment)...');
  try {
    execSync('npm install --production=false', {
      cwd: DASHBOARD_DIR,
      stdio: 'pipe',
      timeout: 120000,
    });
    success('Dependencies installed');
  } catch (e) {
    error('Failed to install dependencies. Run: cd ' + DASHBOARD_DIR + ' && npm install');
    process.exit(1);
  }
}

function applyBranding() {
  const companyPath = path.join(ORCH_DIR, 'company.yaml');
  if (!fs.existsSync(companyPath)) return;

  try {
    const content = fs.readFileSync(companyPath, 'utf8');
    const nameMatch = content.match(/name:\s*["']?(.+?)["']?\s*\n/);
    const companyName = nameMatch ? nameMatch[1] : null;

    if (companyName) {
      // Update layout.tsx title
      const layoutPath = path.join(DASHBOARD_DIR, 'src', 'app', 'layout.tsx');
      if (fs.existsSync(layoutPath)) {
        let layout = fs.readFileSync(layoutPath, 'utf8');
        layout = layout.replace(/title:\s*["'].*?["']/, `title: "${companyName} — Orchestrator"`);
        layout = layout.replace(/description:\s*["'].*?["']/, `description: "${companyName} AI Orchestrator Dashboard"`);
        fs.writeFileSync(layoutPath, layout, 'utf8');
      }
      success(`Branding applied: ${companyName}`);
    }
  } catch {
    // Non-critical — continue
  }
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) {
    error(`Dashboard source not found at: ${src}`);
    error('Make sure you installed the framework correctly.');
    process.exit(1);
  }
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.name === 'node_modules' || entry.name === '.next' || entry.name === '.vercel') continue;
    if (entry.isDirectory()) {
      copyDir(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

// === MAIN ===
const args = process.argv.slice(2);
const port = args.includes('--port') ? args[args.indexOf('--port') + 1] : '3000';

console.log('\n  \x1b[1m\x1b[36mOrchestrator AI\x1b[0m — Dashboard v1.6.0\n');

if (args.includes('--setup') || !fs.existsSync(path.join(DASHBOARD_DIR, 'node_modules'))) {
  setupDashboard();
}

if (args.includes('--build')) {
  log('Building production dashboard...');
  try {
    execSync('npm run build', { cwd: DASHBOARD_DIR, stdio: 'inherit' });
    success('Build complete! Run: orch-dashboard to start');
  } catch {
    error('Build failed');
    process.exit(1);
  }
} else {
  // Start dev server
  log(`Starting dashboard on http://localhost:${port} ...\n`);

  const env = { ...process.env, PORT: port };
  const child = spawn('npm', ['run', 'dev'], {
    cwd: DASHBOARD_DIR,
    stdio: 'inherit',
    env,
    shell: true,
  });

  child.on('error', (err) => {
    error(`Failed to start: ${err.message}`);
    process.exit(1);
  });

  process.on('SIGINT', () => {
    child.kill();
    process.exit(0);
  });
}
