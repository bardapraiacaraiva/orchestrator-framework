#!/usr/bin/env node

/**
 * Orchestrator AI Framework — One-command installer for Claude Code
 *
 * Usage:
 *   npx orchestrator-ai-framework init                          # Interactive
 *   npx orchestrator-ai-framework init --company "Acme" --preset agency
 *   npx orchestrator-ai-framework validate                      # Check installation
 *   npx orchestrator-ai-framework uninstall                     # Remove framework
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { execSync } = require('child_process');

// === CONFIG ===
const HOME = process.env.HOME || process.env.USERPROFILE;
const CLAUDE_HOME = path.join(HOME, '.claude');
const SKILLS_DIR = path.join(CLAUDE_HOME, 'skills');
const ORCH_DIR = path.join(CLAUDE_HOME, 'orchestrator');
const FRAMEWORK_ROOT = path.resolve(__dirname, '..');

const CORE_SKILLS = [
  'orchestrator', 'taskboard', 'dispatch', 'heartbeat',
  'autopilot', 'quality', 'analytics', 'status'
];

const PRESETS = {
  agency: { desc: 'Digital/marketing agency', divisions: ['marketing', 'technical', 'seo', 'client-success'] },
  saas: { desc: 'SaaS product company', divisions: ['engineering', 'product', 'growth', 'support'] },
  studio: { desc: 'Design/architecture studio', divisions: ['design', 'production', 'regulatory'] },
  freelancer: { desc: 'Solo consultant', divisions: ['delivery'] },
  custom: { desc: 'Build your own', divisions: [] }
};

const ORCH_DIRS = [
  'tasks/active', 'tasks/done', 'tasks/templates',
  'audit', 'budgets', 'quality'
];

// === HELPERS ===
function log(msg) { console.log(`  \x1b[36m>\x1b[0m ${msg}`); }
function success(msg) { console.log(`  \x1b[32m✓\x1b[0m ${msg}`); }
function warn(msg) { console.log(`  \x1b[33m!\x1b[0m ${msg}`); }
function error(msg) { console.error(`  \x1b[31m✗\x1b[0m ${msg}`); }

function mkdirSafe(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function copyDir(src, dest) {
  mkdirSafe(dest);
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function replaceInFile(filePath, replacements) {
  let content = fs.readFileSync(filePath, 'utf8');
  for (const [key, value] of Object.entries(replacements)) {
    content = content.replace(new RegExp(key, 'g'), value);
  }
  fs.writeFileSync(filePath, content, 'utf8');
}

async function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(`  \x1b[36m?\x1b[0m ${question} `, answer => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

// === COMMANDS ===

async function init(args) {
  console.log('\n  \x1b[1m\x1b[36mOrchestrator AI Framework\x1b[0m — v1.0.0\n');
  console.log('  Paperclip-inspired orchestration for Claude Code\n');

  // Parse args
  let company = args.find((_, i, a) => a[i - 1] === '--company') || '';
  let preset = args.find((_, i, a) => a[i - 1] === '--preset') || '';
  let owner = args.find((_, i, a) => a[i - 1] === '--owner') || '';
  let licenseKey = args.find((_, i, a) => a[i - 1] === '--license') || '';

  // Interactive if missing
  if (!company) {
    company = await ask('Company/agency name:');
  }
  if (!owner) {
    owner = await ask('Owner name (your name):') || 'owner';
  }
  if (!preset) {
    console.log('\n  Available presets:');
    for (const [key, val] of Object.entries(PRESETS)) {
      console.log(`    \x1b[33m${key.padEnd(12)}\x1b[0m ${val.desc}`);
    }
    preset = await ask('\nPreset [agency/saas/studio/freelancer/custom]:') || 'agency';
  }

  if (!PRESETS[preset]) {
    error(`Unknown preset: ${preset}. Using 'agency'.`);
    preset = 'agency';
  }

  console.log(`\n  Installing for: \x1b[1m${company}\x1b[0m (${preset} preset)\n`);

  // Step 1: Pre-flight checks
  log('Checking Claude Code CLI...');
  try {
    execSync('claude --version', { stdio: 'pipe' });
    success('Claude Code CLI found');
  } catch {
    warn('Claude Code CLI not found — framework will install but CLI needed to use skills');
  }

  // Step 2: Create directories
  log('Creating orchestrator directories...');
  for (const dir of ORCH_DIRS) {
    mkdirSafe(path.join(ORCH_DIR, dir));
  }
  success(`Created ${ORCH_DIRS.length} directories`);

  // Step 3: Install core skills
  log('Installing core skills...');
  let installed = 0;
  for (const skill of CORE_SKILLS) {
    const src = path.join(FRAMEWORK_ROOT, 'core', 'skills', skill);
    const dest = path.join(SKILLS_DIR, `orch-${skill}`);
    if (fs.existsSync(src)) {
      copyDir(src, dest);
      installed++;
    } else {
      warn(`Skill not found: ${skill}`);
    }
  }
  success(`Installed ${installed}/${CORE_SKILLS.length} core skills`);

  // Step 4: Generate company.yaml
  log('Generating company.yaml...');
  const templatePath = path.join(FRAMEWORK_ROOT, 'core', 'config', 'company.template.yaml');
  const destPath = path.join(ORCH_DIR, 'company.yaml');

  if (fs.existsSync(templatePath)) {
    fs.copyFileSync(templatePath, destPath);
    replaceInFile(destPath, {
      '{{COMPANY_NAME}}': company,
      '{{OWNER}}': owner,
      '{{PRESET}}': preset,
      '{{DATE}}': new Date().toISOString().split('T')[0]
    });
    success('Generated company.yaml');
  } else {
    warn('Template not found — creating minimal company.yaml');
    const minimal = `company:\n  name: "${company}"\n  owner: "${owner}"\n  preset: "${preset}"\n  budget:\n    monthly_limit_tokens: 50000000\n    alert_threshold: 0.80\n    auto_pause_threshold: 0.95\n  created: "${new Date().toISOString().split('T')[0]}"\n`;
    fs.writeFileSync(destPath, minimal, 'utf8');
    success('Generated minimal company.yaml');
  }

  // Step 5: Copy infrastructure files
  log('Installing infrastructure...');
  const infraFiles = [
    ['core/config/notifications.yaml', 'orchestrator/notifications.yaml'],
    ['core/config/eval-baseline.template.yaml', 'orchestrator/quality/eval-baseline.yaml'],
    ['core/scripts/budget_tracker.py', 'orchestrator/budget_tracker.py'],
  ];
  for (const [src, dest] of infraFiles) {
    const srcPath = path.join(FRAMEWORK_ROOT, src);
    const destPath = path.join(CLAUDE_HOME, dest);
    if (fs.existsSync(srcPath)) {
      mkdirSafe(path.dirname(destPath));
      fs.copyFileSync(srcPath, destPath);
    }
  }
  success('Installed budget tracker, notifications, eval baseline');

  // Step 6: Initialize budget file
  log('Initializing budget tracker...');
  const month = new Date().toISOString().slice(0, 7);
  const budgetPath = path.join(ORCH_DIR, 'budgets', `${month}.yaml`);
  if (!fs.existsSync(budgetPath)) {
    const budget = `month: "${month}"\ncompany: "${company}"\nlimit: 50000000\ntotal_tokens_used: 0\npercentage: 0.0\nby_project: {}\nby_skill: {}\nby_model:\n  opus: 0\n  sonnet: 0\n  haiku: 0\nalert_80_sent: false\nalert_95_sent: false\nlast_updated: "${new Date().toISOString()}"\npulse_count: 0\n`;
    fs.writeFileSync(budgetPath, budget, 'utf8');
    success(`Initialized budget for ${month}`);
  } else {
    success('Budget file already exists');
  }

  // Step 7: Copy preset-specific config
  log(`Applying ${preset} preset...`);
  const presetPath = path.join(FRAMEWORK_ROOT, 'presets', `${preset}.yaml`);
  if (fs.existsSync(presetPath)) {
    fs.copyFileSync(presetPath, path.join(ORCH_DIR, 'preset.yaml'));
    success(`Applied ${preset} preset`);
  } else {
    warn(`Preset file not found: ${preset}.yaml — using defaults`);
  }

  // Step 8: License setup
  log('Setting up license...');
  const licenseSrc = path.join(FRAMEWORK_ROOT, 'core', 'scripts', 'license.js');
  if (fs.existsSync(licenseSrc)) {
    fs.copyFileSync(licenseSrc, path.join(ORCH_DIR, 'license.js'));
  }

  if (!licenseKey) {
    error('License key required. Get your key at: https://orchestrator-ai-three.vercel.app/#pricing');
    error('Then run: npx orchestrator-ai-framework init --license YOUR-KEY');
    process.exit(1);
  }

  {
    let tier = 'trial';
    if (licenseKey.startsWith('VIP-')) tier = 'vip';
    else if (licenseKey.startsWith('TEAM-')) tier = 'team';
    else if (licenseKey.startsWith('ENT-')) tier = 'enterprise';
    else if (licenseKey.startsWith('PRO-')) tier = 'pro';
    const expires = tier === 'vip' ? null : new Date();
    if (expires) expires.setDate(expires.getDate() + (tier === 'trial' ? 14 : 30));
    const licenseData = {
      version: '1.0', tier, key: licenseKey, email: '',
      issued_at: new Date().toISOString(),
      expires_at: expires ? expires.toISOString() : null,
      last_validated: new Date().toISOString(),
      grace_period_days: tier === 'vip' ? 99999 : 7,
      status: 'active'
    };
    fs.writeFileSync(path.join(ORCH_DIR, '.license'), JSON.stringify(licenseData, null, 2), 'utf8');
    success(tier === 'vip' ? `VIP Lifetime license activated — Full access forever` :
           tier === 'trial' ? `Free trial activated (14 days — expires ${expires.toISOString().split('T')[0]})` :
           `License activated: ${tier} tier (30 days)`);
  }

  // Done
  console.log('\n  \x1b[1m\x1b[32mInstallation complete!\x1b[0m\n');
  console.log('  Next steps:');
  console.log('    1. Add your own skills to ~/.claude/skills/');
  console.log('    2. Edit ~/.claude/orchestrator/company.yaml to add workers');
  console.log('    3. Test: type /orch-orchestrator in Claude Code');
  console.log('    4. Run autopilot: /orch-autopilot');
  if (!licenseKey) {
    console.log('\n  \x1b[33mUpgrade to Pro (€29/mo):\x1b[0m');
    console.log('    npx orchestrator-ai-framework init --license PRO-YOUR-KEY');
  }
  console.log(`\n  Docs: https://github.com/bardapraiacaraiva/orchestrator-framework\n`);
}

function validate() {
  console.log('\n  \x1b[1mValidating installation...\x1b[0m\n');
  let errors = 0;

  // Check dirs
  for (const dir of ORCH_DIRS) {
    const fullPath = path.join(ORCH_DIR, dir);
    if (fs.existsSync(fullPath)) {
      success(`Directory: ${dir}`);
    } else {
      error(`Missing directory: ${dir}`);
      errors++;
    }
  }

  // Check core skills
  for (const skill of CORE_SKILLS) {
    const skillPath = path.join(SKILLS_DIR, `orch-${skill}`, 'SKILL.md');
    if (fs.existsSync(skillPath)) {
      const lines = fs.readFileSync(skillPath, 'utf8').split('\n').length;
      success(`Skill: orch-${skill} (${lines} lines)`);
    } else {
      error(`Missing skill: orch-${skill}`);
      errors++;
    }
  }

  // Check company.yaml
  const companyPath = path.join(ORCH_DIR, 'company.yaml');
  if (fs.existsSync(companyPath) && fs.statSync(companyPath).size > 0) {
    success('company.yaml exists and non-empty');
  } else {
    error('company.yaml missing or empty');
    errors++;
  }

  // Check budget tracker
  const budgetScript = path.join(ORCH_DIR, 'budget_tracker.py');
  if (fs.existsSync(budgetScript)) {
    success('budget_tracker.py exists');
  } else {
    error('budget_tracker.py missing');
    errors++;
  }

  console.log(`\n  Result: ${errors === 0 ? '\x1b[32mPASS\x1b[0m' : `\x1b[31mFAIL (${errors} errors)\x1b[0m`}\n`);
  process.exit(errors > 0 ? 1 : 0);
}

function uninstall() {
  console.log('\n  \x1b[1m\x1b[33mUninstalling Orchestrator AI Framework...\x1b[0m\n');

  // Remove core skills
  for (const skill of CORE_SKILLS) {
    const skillPath = path.join(SKILLS_DIR, `orch-${skill}`);
    if (fs.existsSync(skillPath)) {
      fs.rmSync(skillPath, { recursive: true });
      log(`Removed skill: orch-${skill}`);
    }
  }

  // Note: NOT removing orchestrator dir (may have user data)
  warn('Orchestrator directory preserved (~/.claude/orchestrator/)');
  warn('Remove manually if desired: rm -rf ~/.claude/orchestrator/');

  console.log('\n  \x1b[32mUninstall complete.\x1b[0m\n');
}

// === MAIN ===
const [, , command, ...args] = process.argv;

switch (command) {
  case 'init':
    init(args);
    break;
  case 'validate':
    validate();
    break;
  case 'uninstall':
    uninstall();
    break;
  default:
    console.log(`
  \x1b[1mOrchestrator AI Framework\x1b[0m — v1.0.0

  Usage:
    npx orchestrator-ai-framework init [options]    Install the framework
    npx orchestrator-ai-framework validate          Check installation
    npx orchestrator-ai-framework uninstall         Remove framework

  Options:
    --company "Name"    Company/agency name
    --owner "Name"      Owner name
    --preset <type>     agency | saas | studio | freelancer | custom

  Examples:
    npx orchestrator-ai-framework init
    npx orchestrator-ai-framework init --company "Acme Agency" --preset agency
    npx orchestrator-ai-framework init --preset saas --owner john
`);
}
