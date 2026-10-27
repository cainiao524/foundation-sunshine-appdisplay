import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeAppDisplayProfile, validDisplayResolution, validDisplayRefreshRate } from '../utils/appDisplayProfile.js'

test('fixed host modes enforce the same bounds as the server', () => {
  assert.equal(validDisplayResolution('16384x16384'), true)
  assert.equal(validDisplayResolution('16385x1080'), false)
  assert.equal(validDisplayResolution('1920x1080junk'), false)
  for (const value of ['59.94', '119.88', '0.5', '1000']) assert.equal(validDisplayRefreshRate(value), true)
  for (const value of ['1001', '0', '59.94junk', '1.1234567']) assert.equal(validDisplayRefreshRate(value), false)
})

test('disconnect and dynamic follow survive save and are removed when scheme is disabled', () => {
  const app = { 'display-target': 'virtual', 'display-disconnect-action': 'restore', 'display-dynamic-resolution-follow-display': 'disabled' }
  const normalized = normalizeAppDisplayProfile(app)
  assert.equal(normalized['display-disconnect-action'], 'restore')
  assert.equal(normalized['display-dynamic-resolution-follow-display'], 'disabled')
  assert.deepEqual(normalizeAppDisplayProfile({ ...normalized, 'display-target': '' }), {})
})

test('app without a display scheme keeps no display fields at all', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Desktop',
    'display-target': '',
    'display-device-prep': 'ensure_only_display',
    'display-resolution-mode': 'no_operation',
    'display-obsolete-option': 'legacy',
  })

  assert.deepEqual(normalized, { name: 'Desktop' })
})

test('app display scheme fields are preserved', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'virtual',
    'display-device-prep': 'no_operation',
    'display-resolution-mode': 'client',
    'display-refresh-rate-mode': 'client',
  })

  assert.equal(normalized['display-target'], 'virtual')
  assert.equal(normalized['display-device-prep'], 'no_operation')
  assert.equal(normalized['display-resolution-mode'], 'client')
  assert.equal(normalized['display-refresh-rate-mode'], 'client')
})

test('invalid mode values are cleared', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'physical',
    'display-resolution-mode': 'bogus',
    'display-refresh-rate-mode': 'manual',
  })

  assert.equal(normalized['display-resolution-mode'], '')
  assert.equal(normalized['display-refresh-rate-mode'], '')
})

test('invalid display-target clears the whole profile', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'bogus',
    'display-device-prep': 'ensure_primary',
    'display-resolution-mode': 'client',
    'display-hdr': 'on',
  })

  assert.deepEqual(normalized, { name: 'Game' })
})

test('refresh rate no_operation remains independent of resolution', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'physical',
    'display-refresh-rate-mode': 'no_operation',
  })

  assert.equal(normalized['display-refresh-rate-mode'], 'no_operation')
})

test('invalid fixed values are cleared', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'virtual',
    'display-resolution': 'not-a-resolution',
    'display-refresh-rate': 'abc',
  })

  assert.equal(normalized['display-resolution'], '')
  assert.equal(normalized['display-refresh-rate'], '')
})

test('fixed values survive when well formed', () => {
  const normalized = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'virtual',
    'display-resolution': '2560x1440',
    'display-refresh-rate': '60',
  })

  assert.equal(normalized['display-resolution'], '2560x1440')
  assert.equal(normalized['display-refresh-rate'], '60')
})

test('fixed HDR state must be on/off', () => {
  const on = normalizeAppDisplayProfile({ name: 'G', 'display-target': 'virtual', 'display-hdr': 'on' })
  const off = normalizeAppDisplayProfile({ name: 'G', 'display-target': 'virtual', 'display-hdr': 'off' })
  const bad = normalizeAppDisplayProfile({ name: 'G', 'display-target': 'virtual', 'display-hdr': 'forced' })

  assert.equal(on['display-hdr'], 'on')
  assert.equal(off['display-hdr'], 'off')
  assert.equal(bad['display-hdr'], '')
})

test('display-output-name only kept for a physical target', () => {
  const physical = normalizeAppDisplayProfile({
    name: 'G',
    'display-target': 'physical',
    'display-output-name': '\\\\.\\DISPLAY1',
  })
  const virtual = normalizeAppDisplayProfile({
    name: 'G',
    'display-target': 'virtual',
    'display-output-name': '\\\\.\\DISPLAY1',
  })

  assert.equal(physical['display-output-name'], '\\\\.\\DISPLAY1')
  assert.equal(virtual['display-output-name'], undefined)
})
