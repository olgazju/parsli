/* App — top-level state and routing for the Parsli UI kit. */

function App() {
  const data = window.PARSLI_DATA;

  const [screen, setScreen]           = React.useState('parcels');
  const [devMode, setDevMode]         = React.useState(false);
  const [shipments, setShipments]     = React.useState(data.shipments);
  const [accounts, setAccounts]       = React.useState(data.accounts);
  const [sensors, setSensors]         = React.useState(data.sensors);
  const [languages, setLanguages]     = React.useState(data.languages);
  const [allowlist, setAllowlist]     = React.useState(data.allowlist);
  const [blocklist, setBlocklist]     = React.useState(data.blocklist);
  const [expandedIds, setExpandedIds] = React.useState(() => new Set());
  const [receivedIds, setReceivedIds] = React.useState(() => new Set());
  const [syncingIds, setSyncingIds]   = React.useState(() => new Set());
  const [searchQuery, setSearchQuery] = React.useState('');
  const [filter, setFilter]           = React.useState('all');
  const [toastMsg, setToastMsg]       = React.useState(null);

  const obs = data.observability;

  const stats = React.useMemo(() => {
    const active    = shipments.filter(s => s.current_status !== 'delivered' && !receivedIds.has(s.shipment_id)).length;
    const delivered = shipments.filter(s => s.current_status === 'delivered' || receivedIds.has(s.shipment_id)).length;
    const orderOnly = shipments.filter(s => s.current_status === 'order_confirmed').length;
    const review    = shipments.filter(s => s.needs_review).length;
    return { active_count: active, delivered_count: delivered, order_only_count: orderOnly, needs_review_count: review };
  }, [shipments, receivedIds]);

  React.useEffect(() => {
    if (!toastMsg) return;
    const id = setTimeout(() => setToastMsg(null), 2800);
    return () => clearTimeout(id);
  }, [toastMsg]);

  const onExpand = (id) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const onReceive = (id) => {
    setReceivedIds(prev => {
      const next = new Set(prev);
      const was = next.has(id);
      was ? next.delete(id) : next.add(id);
      setToastMsg({ text: was ? 'Removed from received.' : 'Marked as received.', tone: 'success' });
      return next;
    });
  };

  const onDelete = (id) => {
    const s = shipments.find(x => x.shipment_id === id);
    if (!confirm(`Delete "${s?.display_title || id}"?\n\nThis removes the parcel and its events permanently.`)) return;
    setShipments(prev => prev.filter(x => x.shipment_id !== id));
    setToastMsg({ text: 'Parcel deleted.', tone: 'success' });
  };

  const onConnect = () => {
    const fakeNew = { account_id: 'demo@gmail.com', initial_sync_completed: false, last_sync_at_minutes: null };
    if (accounts.find(a => a.account_id === fakeNew.account_id)) {
      setToastMsg({ text: 'Already connected.', tone: '' });
      return;
    }
    setAccounts(prev => [...prev, fakeNew]);
    setToastMsg({ text: 'Account connected. Starting initial sync…', tone: 'success' });
    setSyncingIds(prev => new Set(prev).add(fakeNew.account_id));
    setTimeout(() => {
      setSyncingIds(prev => { const n = new Set(prev); n.delete(fakeNew.account_id); return n; });
      setAccounts(prev => prev.map(a => a.account_id === fakeNew.account_id
        ? { ...a, initial_sync_completed: true, last_sync_at_minutes: 0 }
        : a));
      setToastMsg({ text: 'Sync complete — 6 new, 142 processed.', tone: 'success' });
    }, 1500);
  };

  const onSync = (id) => {
    if (syncingIds.has(id)) return;
    setSyncingIds(prev => new Set(prev).add(id));
    setTimeout(() => {
      setSyncingIds(prev => { const n = new Set(prev); n.delete(id); return n; });
      setAccounts(prev => prev.map(a => a.account_id === id ? { ...a, last_sync_at_minutes: 0 } : a));
      setToastMsg({ text: 'Sync complete — 2 new, 18 processed.', tone: 'success' });
    }, 1100);
  };

  const onRemove = (id) => {
    if (!confirm(`Remove ${id}?\n\nDisconnects the account and deletes the stored token. Parsed parcels are not affected.`)) return;
    setAccounts(prev => prev.filter(a => a.account_id !== id));
    setToastMsg({ text: 'Account removed.', tone: 'success' });
  };

  const onToggleSensor = (id) => {
    setSensors(prev => prev.map(s => s.id === id ? { ...s, on: !s.on } : s));
  };

  const onToggleLanguage = (code) => {
    setLanguages(prev => {
      const has = prev.enabled.includes(code);
      const next = has
        ? prev.enabled.filter(c => c !== code)
        : [...prev.enabled, code];
      // Don't allow zero languages
      if (next.length === 0) {
        setToastMsg({ text: 'At least one language must stay enabled.', tone: 'error' });
        return prev;
      }
      return { ...prev, enabled: next };
    });
  };

  const onAddAllow = (d) => {
    if (allowlist.includes(d) || blocklist.includes(d)) {
      setToastMsg({ text: 'Domain is already in a list.', tone: '' });
      return;
    }
    setAllowlist(prev => [...prev, d]);
    setToastMsg({ text: `${d} added to allowlist.`, tone: 'success' });
  };
  const onRemoveAllow = (d) => setAllowlist(prev => prev.filter(x => x !== d));
  const onAddBlock = (d) => {
    if (allowlist.includes(d) || blocklist.includes(d)) {
      setToastMsg({ text: 'Domain is already in a list.', tone: '' });
      return;
    }
    setBlocklist(prev => [...prev, d]);
    setToastMsg({ text: `${d} added to blocklist.`, tone: 'success' });
  };
  const onRemoveBlock = (d) => setBlocklist(prev => prev.filter(x => x !== d));

  const onToggleDev = (on) => {
    setDevMode(on);
    if (!on && screen === 'diagnostics') setScreen('parcels');
  };

  return (
    <>
      <Sidebar
        screen={screen}
        onNavigate={setScreen}
        online={accounts.length > 0}
        devMode={devMode}
        onToggleDev={onToggleDev}
      />
      <main className="content">
        {screen === 'parcels' && (
          <ParcelsScreen
            shipments={shipments}
            stats={stats}
            expandedIds={expandedIds}
            receivedIds={receivedIds}
            onExpand={onExpand}
            onReceive={onReceive}
            onDelete={onDelete}
            searchQuery={searchQuery}
            onSearch={setSearchQuery}
            filter={filter}
            onFilter={setFilter}
          />
        )}
        {screen === 'accounts' && (
          <SourcesScreen
            accounts={accounts}
            syncingIds={syncingIds}
            onConnect={onConnect}
            onSync={onSync}
            onRemove={onRemove}
          />
        )}
        {screen === 'preferences' && (
          <PreferencesScreen
            languages={languages}
            onToggleLanguage={onToggleLanguage}
            allowlist={allowlist}
            blocklist={blocklist}
            onAddAllow={onAddAllow}
            onRemoveAllow={onRemoveAllow}
            onAddBlock={onAddBlock}
            onRemoveBlock={onRemoveBlock}
          />
        )}
        {screen === 'diagnostics' && devMode && (
          <DiagnosticsScreen obs={obs} />
        )}
      </main>
      <Toast message={toastMsg?.text} tone={toastMsg?.tone} />
    </>
  );
}

Object.assign(window, { App });
