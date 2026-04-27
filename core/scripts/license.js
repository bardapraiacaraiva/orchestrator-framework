/**
 * Orchestrator AI Framework — License Manager
 *
 * Manages tier-based access control for the framework.
 * License file: ~/.claude/orchestrator/.license
 *
 * Tiers:
 *   community  — Free forever (8 core skills)
 *   pro        — €29/mo (+ playbooks, eval, analytics)
 *   team       — €99/mo (+ multi-user, shared budget)
 *   enterprise — €299/mo (+ custom, SLA, onboarding)
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const HOME = process.env.HOME || process.env.USERPROFILE;
const LICENSE_PATH = path.join(HOME, '.claude', 'orchestrator', '.license');
const VALIDATION_URL = process.env.ORCH_LICENSE_API || 'https://orchestrator-api.vercel.app/api/validate';

// === TIER DEFINITIONS ===
const TIERS = {
  community: {
    name: 'Community',
    price: 0,
    skills: [
      'orch-orchestrator', 'orch-taskboard', 'orch-dispatch', 'orch-heartbeat',
      'orch-autopilot', 'orch-quality', 'orch-analytics', 'orch-status'
    ],
    features: {
      max_parallel: 2,
      playbooks: false,
      eval_calibration: false,
      advanced_analytics: false,
      multi_user: false,
      custom_presets: false,
      priority_support: false
    }
  },
  pro: {
    name: 'Pro',
    price: 29,
    skills: [
      // All community skills +
      'orch-orchestrator', 'orch-taskboard', 'orch-dispatch', 'orch-heartbeat',
      'orch-autopilot', 'orch-quality', 'orch-analytics', 'orch-status',
      // Pro-exclusive skills
      'orch-playbook-manager', 'orch-eval-calibrator', 'orch-advanced-analytics'
    ],
    features: {
      max_parallel: 3,
      playbooks: true,
      eval_calibration: true,
      advanced_analytics: true,
      multi_user: false,
      custom_presets: false,
      priority_support: true
    }
  },
  team: {
    name: 'Team',
    price: 99,
    skills: [
      // All pro skills + team features
      'orch-orchestrator', 'orch-taskboard', 'orch-dispatch', 'orch-heartbeat',
      'orch-autopilot', 'orch-quality', 'orch-analytics', 'orch-status',
      'orch-playbook-manager', 'orch-eval-calibrator', 'orch-advanced-analytics',
      'orch-team-dashboard', 'orch-shared-budget', 'orch-role-access'
    ],
    features: {
      max_parallel: 5,
      playbooks: true,
      eval_calibration: true,
      advanced_analytics: true,
      multi_user: true,
      max_seats: 5,
      custom_presets: false,
      priority_support: true
    }
  },
  enterprise: {
    name: 'Enterprise',
    price: 299,
    skills: ['*'], // All skills
    features: {
      max_parallel: 10,
      playbooks: true,
      eval_calibration: true,
      advanced_analytics: true,
      multi_user: true,
      max_seats: 50,
      custom_presets: true,
      priority_support: true,
      dedicated_onboarding: true,
      sla_guaranteed: true
    }
  }
};

// === LICENSE FILE OPERATIONS ===

function generateLicenseId() {
  return 'ORCH-' + crypto.randomBytes(12).toString('hex').toUpperCase().match(/.{4}/g).join('-');
}

function createLicense(tier, key, expiresAt, email) {
  const license = {
    version: '1.0',
    tier: tier,
    key: key || generateLicenseId(),
    email: email || '',
    issued_at: new Date().toISOString(),
    expires_at: expiresAt || null, // null = never (community)
    last_validated: new Date().toISOString(),
    grace_period_days: 7, // Days of offline access after expiry
    features: TIERS[tier]?.features || TIERS.community.features,
    status: 'active' // active | expired | suspended | grace
  };

  const dir = path.dirname(LICENSE_PATH);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(LICENSE_PATH, JSON.stringify(license, null, 2), 'utf8');
  return license;
}

function readLicense() {
  if (!fs.existsSync(LICENSE_PATH)) {
    // No license = community tier
    return createLicense('community');
  }

  try {
    const raw = fs.readFileSync(LICENSE_PATH, 'utf8');
    const license = JSON.parse(raw);
    return license;
  } catch (e) {
    console.error('License file corrupt. Resetting to community.');
    return createLicense('community');
  }
}

function checkLicenseStatus(license) {
  if (license.tier === 'community') {
    return { valid: true, status: 'active', tier: 'community' };
  }

  if (!license.expires_at) {
    return { valid: true, status: 'active', tier: license.tier };
  }

  const now = new Date();
  const expires = new Date(license.expires_at);
  const graceEnd = new Date(expires);
  graceEnd.setDate(graceEnd.getDate() + (license.grace_period_days || 7));

  if (now < expires) {
    return { valid: true, status: 'active', tier: license.tier, days_remaining: Math.ceil((expires - now) / 86400000) };
  }

  if (now < graceEnd) {
    const grace_days_left = Math.ceil((graceEnd - now) / 86400000);
    return { valid: true, status: 'grace', tier: license.tier, grace_days_left, message: `License expired. Grace period: ${grace_days_left} days remaining.` };
  }

  // Expired past grace
  return { valid: false, status: 'expired', tier: 'community', message: 'License expired. Downgraded to Community tier. Renew at orchestrator-ai.com' };
}

// === FEATURE GATING ===

function canAccessFeature(featureName) {
  const license = readLicense();
  const status = checkLicenseStatus(license);

  if (!status.valid) {
    // Expired — community features only
    return TIERS.community.features[featureName] || false;
  }

  const tier = TIERS[status.tier];
  if (!tier) return false;

  return tier.features[featureName] || false;
}

function canAccessSkill(skillName) {
  const license = readLicense();
  const status = checkLicenseStatus(license);

  const tier = status.valid ? status.tier : 'community';
  const tierConfig = TIERS[tier];

  if (!tierConfig) return false;
  if (tierConfig.skills[0] === '*') return true; // Enterprise = all

  return tierConfig.skills.includes(skillName);
}

function getMaxParallel() {
  const license = readLicense();
  const status = checkLicenseStatus(license);
  const tier = status.valid ? status.tier : 'community';
  return TIERS[tier]?.features?.max_parallel || 2;
}

// === ONLINE VALIDATION ===

async function validateOnline(license) {
  if (license.tier === 'community') return { valid: true, status: 'active' };

  try {
    const https = require('https');
    const url = new URL(VALIDATION_URL);

    const postData = JSON.stringify({
      key: license.key,
      tier: license.tier,
      email: license.email
    });

    return new Promise((resolve) => {
      const req = https.request({
        hostname: url.hostname,
        path: url.pathname,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': postData.length },
        timeout: 5000
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(data);
            if (result.valid && result.expires_at) {
              // Update local license with server expiry
              license.expires_at = result.expires_at;
              license.last_validated = new Date().toISOString();
              license.status = result.status || 'active';
              fs.writeFileSync(LICENSE_PATH, JSON.stringify(license, null, 2), 'utf8');
            }
            resolve(result);
          } catch {
            resolve({ valid: true, offline: true }); // Network issue = allow (grace)
          }
        });
      });

      req.on('error', () => resolve({ valid: true, offline: true }));
      req.on('timeout', () => { req.destroy(); resolve({ valid: true, offline: true }); });
      req.write(postData);
      req.end();
    });
  } catch {
    return { valid: true, offline: true }; // Fail open with grace
  }
}

// === SUSPENSION ===

function suspendLicense(reason) {
  const license = readLicense();
  license.status = 'suspended';
  license.suspended_at = new Date().toISOString();
  license.suspended_reason = reason || 'payment_failed';
  license.expires_at = new Date().toISOString(); // Expire immediately
  fs.writeFileSync(LICENSE_PATH, JSON.stringify(license, null, 2), 'utf8');
  return license;
}

function reactivateLicense(newExpiresAt) {
  const license = readLicense();
  license.status = 'active';
  license.expires_at = newExpiresAt;
  license.last_validated = new Date().toISOString();
  delete license.suspended_at;
  delete license.suspended_reason;
  fs.writeFileSync(LICENSE_PATH, JSON.stringify(license, null, 2), 'utf8');
  return license;
}

// === CLI ===

function printStatus() {
  const license = readLicense();
  const status = checkLicenseStatus(license);
  const tier = TIERS[license.tier] || TIERS.community;

  console.log('\n  Orchestrator AI — License Status\n');
  console.log(`  Tier:       ${tier.name} (€${tier.price}/mo)`);
  console.log(`  Key:        ${license.key}`);
  console.log(`  Status:     ${status.status.toUpperCase()}`);
  console.log(`  Email:      ${license.email || 'not set'}`);
  console.log(`  Issued:     ${license.issued_at}`);
  console.log(`  Expires:    ${license.expires_at || 'never'}`);
  console.log(`  Validated:  ${license.last_validated}`);

  if (status.days_remaining) console.log(`  Days left:  ${status.days_remaining}`);
  if (status.grace_days_left) console.log(`  Grace left: ${status.grace_days_left} days`);
  if (status.message) console.log(`\n  ⚠ ${status.message}`);

  console.log('\n  Features:');
  for (const [feature, value] of Object.entries(tier.features)) {
    const icon = value === true ? '✓' : value === false ? '✗' : value;
    console.log(`    ${feature.padEnd(25)} ${icon}`);
  }
  console.log();
}

// === EXPORTS ===
module.exports = {
  TIERS,
  createLicense,
  readLicense,
  checkLicenseStatus,
  canAccessFeature,
  canAccessSkill,
  getMaxParallel,
  validateOnline,
  suspendLicense,
  reactivateLicense,
  printStatus,
  LICENSE_PATH
};

// CLI usage
if (require.main === module) {
  const [,, cmd, ...args] = process.argv;

  switch (cmd) {
    case 'status':
      printStatus();
      break;
    case 'activate':
      const [tier, key, email] = args;
      if (!tier || !key) {
        console.log('Usage: license.js activate <tier> <key> [email]');
        break;
      }
      const expires = new Date();
      expires.setDate(expires.getDate() + 30);
      createLicense(tier, key, expires.toISOString(), email);
      console.log(`License activated: ${tier} tier, expires ${expires.toISOString()}`);
      break;
    case 'suspend':
      suspendLicense(args[0] || 'manual');
      console.log('License suspended.');
      break;
    case 'check':
      const license = readLicense();
      const result = checkLicenseStatus(license);
      console.log(JSON.stringify(result, null, 2));
      process.exit(result.valid ? 0 : 1);
      break;
    default:
      console.log(`
  Orchestrator AI — License Manager

  Commands:
    status                          Show current license
    activate <tier> <key> [email]   Activate a license
    suspend [reason]                Suspend license
    check                           Check validity (exit 1 if invalid)

  Tiers: community, pro, team, enterprise
      `);
  }
}
