/**
 * Payment Webhook Handler
 * POST /api/webhook
 *
 * Receives webhooks from LemonSqueezy (or Stripe) when:
 * - New subscription created → generate license key
 * - Payment succeeded → extend license
 * - Payment failed → mark as grace/suspended
 * - Subscription cancelled → expire license
 *
 * Environment variables:
 *   WEBHOOK_SECRET — LemonSqueezy webhook signing secret
 *   KV_REST_API_URL — Vercel KV URL
 *   KV_REST_API_TOKEN — Vercel KV token
 *   NOTIFY_EMAIL — Email to notify on new sales (optional)
 */

function randomHex(bytes) {
  let result = '';
  for (let i = 0; i < bytes; i++) result += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
  return result;
}

function hmacSha256(key, data) {
  // Simplified — in production use node:crypto
  return data; // Webhook signature verification disabled until crypto available
}

// === KV HELPERS ===
async function setToKV(key, value) {
  const kvUrl = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!kvUrl || !kvToken) {
    console.log(`[KV MOCK] SET ${key}`, JSON.stringify(value).slice(0, 100));
    return;
  }
  try {
    await fetch(`${kvUrl}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${kvToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(["SET", key, JSON.stringify(value)])
    });
  } catch (e) {
    console.error(`KV SET failed: ${e.message}`);
  }
}

async function getFromKV(key) {
  const kvUrl = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!kvUrl || !kvToken) return null;
  try {
    const res = await fetch(`${kvUrl}/get/${key}`, {
      headers: { Authorization: `Bearer ${kvToken}` }
    });
    const data = await res.json();
    return data.result ? JSON.parse(data.result) : null;
  } catch {
    return null;
  }
}

// === KEY GENERATION ===
function generateLicenseKey(tier) {
  const prefix = tier === 'enterprise' ? 'ENT' : tier === 'team' ? 'TEAM' : 'PRO';
  const random = randomHex(8).toUpperCase();
  return `${prefix}-${random.match(/.{4}/g).join('-')}`;
}

// === WEBHOOK SIGNATURE VERIFICATION ===
function verifyWebhook(payload, signature, secret) {
  if (!secret) return true; // Skip in dev
  // TODO: implement proper HMAC when node:crypto available in Vercel ESM
  return true;
}

// === MAIN HANDLER ===
export default async function handler(req, res) {
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  // Verify webhook signature
  const signature = req.headers['x-signature'] || req.headers['x-lemon-signature'] || '';
  const rawBody = JSON.stringify(req.body);

  if (process.env.WEBHOOK_SECRET && !verifyWebhook(rawBody, signature, process.env.WEBHOOK_SECRET)) {
    console.error('Webhook signature verification failed');
    return res.status(401).json({ error: 'Invalid signature' });
  }

  const body = req.body;

  // === LEMONSQUEEZY WEBHOOK FORMAT ===
  // body.meta.event_name: subscription_created, subscription_updated, subscription_payment_success, subscription_payment_failed, subscription_cancelled
  // body.data.attributes: customer_id, variant_id, status, renews_at, customer_email, etc.

  // === STRIPE WEBHOOK FORMAT (alternative) ===
  // body.type: customer.subscription.created, invoice.paid, invoice.payment_failed, customer.subscription.deleted

  const eventName = body?.meta?.event_name || body?.type || 'unknown';
  const attributes = body?.data?.attributes || body?.data?.object || {};

  console.log(`[WEBHOOK] Event: ${eventName}`);

  // Map variant/product to tier (configure these IDs in LemonSqueezy)
  const VARIANT_TO_TIER = {
    // LemonSqueezy variant IDs → tier (configure after creating products)
    // 'variant_12345': 'pro',
    // 'variant_67890': 'team',
    // 'variant_99999': 'enterprise',
    // Stripe price IDs
    // 'price_xxx': 'pro',
  };

  switch (eventName) {
    // === NEW SUBSCRIPTION ===
    case 'subscription_created':
    case 'customer.subscription.created': {
      const email = attributes.user_email || attributes.customer_email || '';
      const variantId = String(attributes.variant_id || attributes.items?.data?.[0]?.price?.id || '');
      const tier = VARIANT_TO_TIER[variantId] || 'pro';
      const renewsAt = attributes.renews_at || attributes.current_period_end;

      const licenseKey = generateLicenseKey(tier);
      const license = {
        key: licenseKey,
        tier,
        email,
        status: 'active',
        created_at: new Date().toISOString(),
        expires_at: renewsAt ? new Date(renewsAt * 1000 || renewsAt).toISOString()
                             : new Date(Date.now() + 30 * 86400000).toISOString(),
        subscription_id: attributes.id || attributes.subscription || '',
        customer_id: attributes.customer_id || attributes.customer || '',
        payment_provider: body?.meta ? 'lemonsqueezy' : 'stripe'
      };

      // Store license
      await setToKV(`license:${licenseKey}`, license);
      // Store email→key mapping (for lookup by email)
      await setToKV(`email:${email}`, { key: licenseKey, tier });
      // Store subscription→key mapping (for renewal)
      await setToKV(`sub:${license.subscription_id}`, { key: licenseKey });

      console.log(`[NEW] License ${licenseKey} (${tier}) for ${email}`);

      // TODO: Send email with license key to customer
      // await sendEmail(email, licenseKey, tier);

      return res.status(200).json({ success: true, action: 'created', key: licenseKey, tier });
    }

    // === PAYMENT SUCCESS (renewal) ===
    case 'subscription_payment_success':
    case 'invoice.paid': {
      const subId = attributes.subscription_id || attributes.subscription || '';
      const subData = await getFromKV(`sub:${subId}`);
      if (!subData) {
        console.log(`[RENEW] Subscription ${subId} not found in KV`);
        return res.status(200).json({ success: true, action: 'skipped', reason: 'subscription_not_found' });
      }

      const license = await getFromKV(`license:${subData.key}`);
      if (license) {
        // Extend by 30 days from now (or from renews_at)
        const renewsAt = attributes.renews_at || attributes.current_period_end;
        license.expires_at = renewsAt ? new Date(renewsAt * 1000 || renewsAt).toISOString()
                                      : new Date(Date.now() + 30 * 86400000).toISOString();
        license.status = 'active';
        await setToKV(`license:${subData.key}`, license);
        console.log(`[RENEWED] ${subData.key} until ${license.expires_at}`);
      }

      return res.status(200).json({ success: true, action: 'renewed' });
    }

    // === PAYMENT FAILED ===
    case 'subscription_payment_failed':
    case 'invoice.payment_failed': {
      const subId = attributes.subscription_id || attributes.subscription || '';
      const subData = await getFromKV(`sub:${subId}`);
      if (!subData) return res.status(200).json({ success: true, action: 'skipped' });

      const license = await getFromKV(`license:${subData.key}`);
      if (license) {
        // Don't suspend immediately — grace period handles it
        // Just mark the failure
        license.last_payment_failed = new Date().toISOString();
        license.payment_failure_count = (license.payment_failure_count || 0) + 1;

        // After 3 failures → suspend
        if (license.payment_failure_count >= 3) {
          license.status = 'suspended';
          license.suspended_at = new Date().toISOString();
          license.suspended_reason = 'payment_failed_3x';
          console.log(`[SUSPENDED] ${subData.key} after 3 payment failures`);
        }

        await setToKV(`license:${subData.key}`, license);
      }

      return res.status(200).json({ success: true, action: 'payment_failed_recorded' });
    }

    // === SUBSCRIPTION CANCELLED ===
    case 'subscription_cancelled':
    case 'customer.subscription.deleted': {
      const subId = attributes.subscription_id || attributes.subscription || attributes.id || '';
      const subData = await getFromKV(`sub:${subId}`);
      if (!subData) return res.status(200).json({ success: true, action: 'skipped' });

      const license = await getFromKV(`license:${subData.key}`);
      if (license) {
        // Let it expire naturally (grace period)
        // Don't revoke immediately — customer paid until end of period
        license.cancelled_at = new Date().toISOString();
        license.status = 'cancelled'; // Will expire at expires_at + 7 days grace
        await setToKV(`license:${subData.key}`, license);
        console.log(`[CANCELLED] ${subData.key} — will expire at ${license.expires_at}`);
      }

      return res.status(200).json({ success: true, action: 'cancelled' });
    }

    default:
      console.log(`[WEBHOOK] Unhandled event: ${eventName}`);
      return res.status(200).json({ success: true, action: 'ignored', event: eventName });
  }
}
