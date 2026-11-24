import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { normalizeAppDisplayProfile } from '../utils/appDisplayProfile.js'

const editor = readFileSync(new URL('../components/AppEditor.vue', import.meta.url), 'utf8')
const template = editor.slice(editor.indexOf('<template>'), editor.indexOf('<script setup>'))
const script = editor.slice(editor.indexOf('<script setup>'), editor.indexOf('</script>'))

const DISPLAY_FIELDS = [
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
]

test('the 1123 editor keeps a Material display-profile section before the advanced gate', () => {
  assert.ok(template.includes("t('apps.display_profile_title')"))
  assert.ok(template.includes('appDisplayOutput'))
  assert.ok(template.includes('fixedValuesEnabled'))
  assert.ok(template.includes('MChoiceItem'))
  assert.ok(!template.includes('DisplayPreparationPicker'))
  assert.ok(!template.includes('DisplayRuleRadioGroup'))
  assert.ok(!template.includes('NewDisplayOutputSelector'))
  const sectionAt = template.indexOf("t('apps.display_profile_title')")
  const gateAt = template.indexOf('v-if="!showAdvanced"')
  assert.ok(sectionAt > 0 && sectionAt < gateAt)
})

test('every saved display-profile field is still bound and normalized on save', () => {
  for (const key of DISPLAY_FIELDS) {
    assert.ok(template.includes(`['${key}']`) || script.includes(`['${key}']`), `${key} is in the editor`)
  }
  assert.ok(script.includes('normalizeAppDisplayProfile(withoutCoverReport(formData.value))'))
  assert.ok(script.includes('displayProfileValid'))
})

test('clearing a scheme still drops every display field, and a bound scheme keeps its fields', () => {
  const bound = normalizeAppDisplayProfile({
    name: 'Game',
    'display-target': 'physical',
    'display-output-name': 'physical-monitor',
    'display-device-prep': 'ensure_primary',
    'display-resolution': '2560x1440',
    'display-refresh-rate': '59.94',
    'display-resolution-mode': 'no_operation',
    'display-refresh-rate-mode': 'client',
    'display-hdr': 'off',
    'display-disconnect-action': 'restore',
    'display-dynamic-resolution-follow-display': 'disabled',
  })
  assert.equal(bound['display-target'], 'physical')
  assert.equal(bound['display-output-name'], 'physical-monitor')
  assert.equal(bound['display-resolution'], '2560x1440')
  assert.equal(bound['display-refresh-rate'], '59.94')
  assert.equal(bound['display-hdr'], 'off')
  assert.deepEqual(normalizeAppDisplayProfile({ ...bound, 'display-target': '' }), { name: 'Game' })
})
