/* Mock fixtures for the Parsli UI kit click-through.
   Faithful to the shape of /api/dashboard/projection in the live backend. */

window.PARSLI_DATA = {
  accounts: [
    { account_id: 'olga@example.com',  initial_sync_completed: true,  last_sync_at_minutes: 14 },
    { account_id: 'jordan@gmail.com',  initial_sync_completed: true,  last_sync_at_minutes: 92 },
  ],

  shipments: [
    {
      shipment_id: 's-001',
      display_title: 'Cotton crew socks (5-pack)',
      display_merchant: 'Uniqlo',
      tracking_number: 'LX894521209HK',
      order_number: null,
      current_status: 'in_transit',
      current_status_label: 'in transit',
      events_count: 4,
      last_status_date: '2h',
      needs_review: false,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 14', evidence: 'Order #UN-7741092 confirmed. Shipping in 1-2 business days.' },
        { status: 'shipped', status_label: 'shipped', event_date: 'Jun 16', evidence: 'Package handed to carrier in Hong Kong. Tracking: LX894521209HK.' },
        { status: 'arrived_in_destination_country', status_label: 'arrived in country', event_date: 'Jun 19', evidence: 'Inbound shipment cleared at customs hub. ETA 2-3 days.' },
        { status: 'in_transit', status_label: 'in transit', event_date: 'Jun 20', evidence: 'Departed regional sort facility. On its way to local carrier.' },
      ],
    },
    {
      shipment_id: 's-002',
      display_title: 'KitchenAid stand mixer (cream)',
      display_merchant: 'Williams Sonoma',
      tracking_number: '1Z999AA10123456784',
      order_number: 'WS-99412',
      current_status: 'out_for_delivery',
      current_status_label: 'out for delivery',
      events_count: 5,
      last_status_date: '34m',
      needs_review: false,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 12', evidence: 'Thank you for your order! Your KitchenAid is being prepared.' },
        { status: 'shipped', status_label: 'shipped', event_date: 'Jun 14', evidence: 'Shipped via UPS Ground.' },
        { status: 'in_transit', status_label: 'in transit', event_date: 'Jun 17', evidence: 'Departed UPS facility in Worldway, CA.' },
        { status: 'handed_to_local_carrier', status_label: 'with local carrier', event_date: 'Jun 20', evidence: 'Arrived at local UPS facility. Expected delivery today.' },
        { status: 'out_for_delivery', status_label: 'out for delivery', event_date: 'Jun 20', evidence: 'On the truck. Delivery between 11:00 AM and 3:00 PM.' },
      ],
    },
    {
      shipment_id: 's-003',
      display_title: 'Field Notes — Workshop Companion 3-pack',
      display_merchant: 'Field Notes Brand',
      tracking_number: '9400111202555283762819',
      order_number: 'FN-1289-Q',
      current_status: 'action_required',
      current_status_label: 'action required',
      events_count: 3,
      last_status_date: '6h',
      needs_review: true,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 10', evidence: 'Order received. Will ship within 2 business days.' },
        { status: 'shipped', status_label: 'shipped', event_date: 'Jun 12', evidence: 'USPS pickup scheduled. Tracking number issued.' },
        { status: 'action_required', status_label: 'action required', event_date: 'Jun 18', evidence: 'Delivery attempted. Signature required — please reschedule or pick up at local USPS branch within 5 days.' },
      ],
    },
    {
      shipment_id: 's-004',
      display_title: 'Replacement coffee carafe',
      display_merchant: 'Bodum',
      tracking_number: null,
      order_number: 'BO-44721',
      current_status: 'delivered',
      current_status_label: 'delivered',
      events_count: 4,
      last_status_date: '2d',
      needs_review: false,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 8', evidence: 'Order #BO-44721 confirmed.' },
        { status: 'shipped', status_label: 'shipped', event_date: 'Jun 10', evidence: 'Shipped from Bodum warehouse.' },
        { status: 'out_for_delivery', status_label: 'out for delivery', event_date: 'Jun 18', evidence: 'On the truck for delivery today.' },
        { status: 'delivered', status_label: 'delivered', event_date: 'Jun 18', evidence: 'Left at front door. Photo attached to original email.' },
      ],
    },
    {
      shipment_id: 's-005',
      display_title: 'Vintage Olivetti ribbon (black)',
      display_merchant: 'Etsy · TypewriterRevival',
      tracking_number: 'RR123456789DE',
      order_number: null,
      current_status: 'customs_pending',
      current_status_label: 'customs pending',
      events_count: 4,
      last_status_date: '1d',
      needs_review: false,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 7', evidence: 'Order placed. Ships from Berlin.' },
        { status: 'shipped', status_label: 'shipped', event_date: 'Jun 9', evidence: 'Tracking number issued: RR123456789DE.' },
        { status: 'arrived_in_destination_country', status_label: 'arrived in country', event_date: 'Jun 16', evidence: 'Inbound shipment received at international hub.' },
        { status: 'customs_pending', status_label: 'customs pending', event_date: 'Jun 19', evidence: 'Held for customs review. Typical delay: 2-4 business days.' },
      ],
    },
    {
      shipment_id: 's-006',
      display_title: 'Standing desk converter',
      display_merchant: 'Fully',
      tracking_number: null,
      order_number: '5594201',
      current_status: 'order_confirmed',
      current_status_label: 'order confirmed',
      events_count: 1,
      last_status_date: '4h',
      needs_review: false,
      events: [
        { status: 'order_confirmed', status_label: 'order confirmed', event_date: 'Jun 20', evidence: 'Thanks for your order. Ships in 3-5 business days.' },
      ],
    },
  ],

  stats: {
    active_count: 4,
    delivered_count: 1,
    order_only_count: 1,
    needs_review_count: 1,
  },

  sensors: [
    { id: 'gmail',  ic: '📧', name: 'Email',       label: 'Gmail',       on: true  },
    { id: 'sms',    ic: '💬', name: 'SMS',         label: 'Text messages', on: false },
    { id: 'voice',  ic: '🎙️', name: 'Voice',       label: 'Call notes',  on: false },
    { id: 'screen', ic: '📸', name: 'Screenshots', label: 'Order pages', on: false },
  ],

  languages: {
    available: [
      { code: 'en', name: 'English',  native: 'English' },
      { code: 'he', name: 'Hebrew',   native: 'עברית' },
    ],
    enabled: ['en', 'he'],
  },

  allowlist: [
    'tracking.dhl.com',
    'mail.uniqlo.com',
    'shipment-tracking.amazon.com',
    'orders.etsy.com',
  ],
  blocklist: [
    'marketing.shein.com',
    'newsletter.aliexpress.com',
  ],

  observability: {
    pipeline: [
      { stage: 'Ingested',   value: 4218, sub: 'last 60 days' },
      { stage: 'Processed',  value: 4218, sub: '100% coverage' },
      { stage: 'Relevant',   value: 312,  sub: '7.4% of total' },
      { stage: 'Ignored',    value: 3906, sub: 'rule-filtered' },
    ],
    method_breakdown: [
      { method: 'rule_match',        count: 2841, ms_avg: 0 },
      { method: 'rule_relevant',     count: 268,  ms_avg: 0 },
      { method: 'model_classified',  count: 44,   ms_avg: 1124 },
      { method: 'model_skipped',     count: 1065, ms_avg: 0 },
    ],
    recent_processing: [
      { id: 'a7c41f3e21b8', status: 'in_transit',       method: 'rule_match',       ms: null,  relevant: true,  review: false },
      { id: 'd92fa18820cc', status: 'order_confirmed',  method: 'rule_match',       ms: null,  relevant: true,  review: false },
      { id: 'b3ee019204ff', status: null,               method: 'rule_ignore',      ms: null,  relevant: false, review: false, reason: 'sender_blocked' },
      { id: '11fc903a8d44', status: 'action_required',  method: 'model_classified', ms: 1287,  relevant: true,  review: true  },
      { id: 'ccef401aa311', status: null,               method: 'rule_ignore',      ms: null,  relevant: false, review: false, reason: 'no_parcel_signals' },
      { id: '20b918cc99ee', status: 'delivered',        method: 'rule_match',       ms: null,  relevant: true,  review: false },
      { id: '0a44ba29c2e1', status: 'customs_pending',  method: 'model_classified', ms: 942,   relevant: true,  review: false },
    ],
    query_batches: [
      {
        id: 'batch-7c1f',
        started_at_minutes_ago: 14,
        runs: [
          { name: 'tracking_keywords_en', count: 18, ms: 142 },
          { name: 'shipping_keywords_he', count: 6,  ms: 88 },
          { name: 'merchant_allowlist',   count: 24, ms: 211 },
        ],
      },
      {
        id: 'batch-3a02',
        started_at_minutes_ago: 92,
        runs: [
          { name: 'tracking_keywords_en', count: 12, ms: 119 },
          { name: 'shipping_keywords_he', count: 4,  ms: 71 },
          { name: 'merchant_allowlist',   count: 17, ms: 188 },
        ],
      },
    ],
  },
};
