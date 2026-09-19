(expectedDeviceId) => {
  // Based on vivo's public app.2b07c6d0.js and chunk-c3f73aa4.efd60a15.js.
  // Live verification is still required; never choose a different device.
  const root = Array.from(document.querySelectorAll('*')).map(el => el.__vue__).find(Boolean);
  if (!root || !expectedDeviceId) throw new Error('Missing app or device binding');
  const store = root.$store;
  const selected = store?.getters?.['device/selected'];
  let position, source;
  if (String(expectedDeviceId).startsWith('share:')) {
    const shared = store?.state.share;
    const id = String(expectedDeviceId).slice(6);
    if (shared?.componentName !== 'ShareDetail' || shared.familyOpenid !== id) return null;
    if (shared.shareInfoObj?.shareInfo?.sharedBy !== 2) return null;
    position = shared.shareInfoObj?.lastLocation;
    source = 'share.shareInfoObj.lastLocation';
  } else if (selected && String(selected.id) === String(expectedDeviceId)) {
    position = selected.location;
    source = 'device/selected.location';
  } else {
    const stack = [root];
    while (stack.length) {
      const vm = stack.pop();
      if (vm.$options?.name === 'Bound' && String(vm.targetDevice?.id) === String(expectedDeviceId)) {
        if (vm.locationStatus !== 'locateSuccess') return null;
        position = vm.position;
        source = 'Bound.position';
        break;
      }
      stack.push(...(vm.$children || []));
    }
  }
  const fixTime = source === 'share.shareInfoObj.lastLocation' ? position?.ctime : position?.time;
  if (!fixTime || position.latitude == null || position.longitude == null) return null;
  const rawTime = Number(fixTime);
  if (!Number.isFinite(rawTime)) throw new Error('Unsupported fix timestamp');
  return {
    lat: Number(position.latitude), lon: Number(position.longitude),
    timestamp: rawTime > 1e12 ? rawTime / 1000 : rawTime,
    accuracy: null, crs: 'BD09', address: position.locationDesc || '',
    device_id: String(expectedDeviceId), source
  };
}
