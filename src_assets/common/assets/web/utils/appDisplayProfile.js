const DISPLAY_PROFILE_FIELDS = new Set([
  'display-target',
  'display-device-prep',
  'display-resolution-mode',
  'display-refresh-rate-mode',
  'display-output-name',
  'display-resolution',
  'display-refresh-rate',
  'display-hdr',
  'display-disconnect-action',
  'display-dynamic-resolution-follow-display',
])

export function validDisplayResolution(value) {
  return /^[1-9]\d{0,4}x[1-9]\d{0,4}$/.test(value) && value.split('x').every((part) => Number(part) <= 16384)
}

export function validDisplayRefreshRate(value) {
  return /^\d+(?:\.\d{1,6})?$/.test(value) && Number(value) > 0 && Number(value) <= 1000
}

/**
 * Normalize the per-app display scheme fields before saving.
 *
 * Apps without a display target keep no display fields at all, so the client
 * request and the global configuration stay fully in control. Apps with a
 * target only keep valid values. Fixed resolution / refresh rate override
 * the matching mode without discarding it; HDR must be a supported policy.
 */
export function normalizeAppDisplayProfile(app) {
  const normalized = { ...app }

  for (const key of Object.keys(normalized)) {
    if (key.startsWith('display-') && !DISPLAY_PROFILE_FIELDS.has(key)) delete normalized[key]
  }

  if (!['physical', 'virtual'].includes(normalized['display-target'])) {
    for (const key of DISPLAY_PROFILE_FIELDS) delete normalized[key]
    return normalized
  }

  if (!['', 'no_operation', 'client'].includes(normalized['display-resolution-mode'])) {
    normalized['display-resolution-mode'] = ''
  }
  if (!['', 'no_operation', 'client'].includes(normalized['display-refresh-rate-mode'])) {
    normalized['display-refresh-rate-mode'] = ''
  }
  if (normalized['display-resolution'] && !validDisplayResolution(normalized['display-resolution'])) {
    normalized['display-resolution'] = ''
  }
  if (normalized['display-refresh-rate'] && !validDisplayRefreshRate(normalized['display-refresh-rate'])) {
    normalized['display-refresh-rate'] = ''
  }
  if (!['', 'on', 'off', 'client', 'no_operation'].includes(normalized['display-hdr'])) {
    normalized['display-hdr'] = ''
  }
  if (normalized['display-target'] !== 'physical') delete normalized['display-output-name']
  for (const [field, values] of Object.entries({
    'display-device-prep': ['', 'no_operation', 'ensure_active', 'ensure_primary', 'ensure_secondary', 'ensure_only_display'],
    'display-disconnect-action': ['', 'keep', 'restore'],
    'display-dynamic-resolution-follow-display': ['', 'enabled', 'disabled'],
  })) {
    if (!values.includes(normalized[field])) normalized[field] = ''
  }
  return normalized
}
