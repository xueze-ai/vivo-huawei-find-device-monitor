import math
import time


def distance(a, b):
    lat1, lat2 = map(math.radians, (a['lat'], b['lat']))
    dl = math.radians(b['lat'] - a['lat'])
    dn = math.radians(b['lon'] - a['lon'])
    h = math.sin(dl / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dn / 2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def evaluate(fix, state, config, now=None):
    """Validate a fix and update movement/geofence state."""
    now = time.time() if now is None else now
    for key in ('lat', 'lon', 'timestamp'):
        if not isinstance(fix.get(key), (float, int)) or not math.isfinite(fix[key]):
            raise ValueError('定位数据不完整')
    accuracy = fix.get('accuracy')
    if accuracy is not None and (not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or accuracy < 0):
        raise ValueError('无效定位精度')
    if not -90 <= fix['lat'] <= 90 or not -180 <= fix['lon'] <= 180:
        raise ValueError('定位数据越界')
    if fix.get('crs') != config['crs']:
        raise ValueError('定位与围栏坐标系不一致')
    old = state.get('fix')
    if fix['timestamp'] > now + 30 or now - fix['timestamp'] > config['max_age_seconds'] or (old and fix['timestamp'] <= old['timestamp']):
        return dict(state), '手机离线或定位未更新', '本轮没有取得新定位；手机可能离线或 vivo 尚未刷新位置。'
    updated = dict(state)
    zones = dict(state.get('zones', {}))
    events, lines = [], []
    if old:
        meters = distance(old, fix)
        updated['last_step_meters'] = meters
        lines.append(f'相比上次有效定位：直线距离约 {meters:.0f} 米')
    else:
        updated['last_step_meters'] = None
        lines.append('首次有效定位，建立基准')
    for zone in config['zones']:
        d = distance(fix, zone)
        current = 'inside' if d <= zone['radius_meters'] else 'outside'
        previous = zones.get(zone['name'])
        if previous and previous != current:
            events.append(('到达' if current == 'inside' else '离开') + zone['name'])
        zones[zone['name']] = current
        label = '区域内' if current == 'inside' else '区域外'
        lines.append(f"{zone['name']}：{label}（距中心约 {d:.0f} 米）")
    updated['fix'] = fix
    updated['zones'] = zones
    return updated, '；'.join(events) or '定位更新', '\n\n'.join(lines)
