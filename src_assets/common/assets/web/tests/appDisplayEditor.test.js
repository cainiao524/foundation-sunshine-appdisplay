import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
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
  assert.ok(template.includes('MDisplayCards'))
  assert.ok(template.includes('MPrepSeg'))
  assert.ok(template.includes('MSeg'))
  assert.ok(template.includes('MExpander'))
  assert.ok(template.includes("t('config.display_device_options_note_windows')"))
  assert.ok(!template.includes('DisplayPreparationPicker'))
  assert.ok(!template.includes('DisplayRuleRadioGroup'))
  assert.ok(!template.includes('NewDisplayOutputSelector'))
  const sectionAt = template.indexOf("t('apps.display_profile_title')")
  const gateAt = template.indexOf('v-if="!showAdvanced"')
  assert.ok(sectionAt > 0 && sectionAt < gateAt)
  const groupAt = template.indexOf('<MGroup>', sectionAt)
  const groupEnd = template.indexOf('</MGroup>', groupAt)
  const group = template.slice(groupAt, groupEnd)
  assert.ok(group.includes('appResolutionRule'))
  assert.equal(group.includes('<MFooter'), false)
  const advancedAt = template.indexOf("t('apps.display_profile_advanced_title')")
  const sectionEnd = template.indexOf('</MSection>', sectionAt)
  assert.ok(advancedAt > sectionEnd && advancedAt < gateAt)
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

const PREP_MODES = ['no_operation', 'ensure_active', 'ensure_primary', 'ensure_secondary', 'ensure_only_display']
const LOCALE_DIR = new URL('../public/assets/locale/', import.meta.url)

function flattenMessages(value, prefix = '') {
  const out = {}
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      Object.assign(out, flattenMessages(child, prefix ? `${prefix}.${key}` : key))
    }
    return out
  }
  out[prefix] = value
  return out
}

function displayEditorKeys() {
  const source = `${template}\n${script}`
  const keys = new Set()
  for (const match of source.matchAll(/\bt\(\s*(['"`])([^'"`]+)\1/g)) {
    const key = match[2]
    if (
      key.startsWith('apps.display_profile_')
      || key.startsWith('config.display_device_')
      || key === 'config.output_name_windows'
      || key === '_common.cancel'
    ) {
      if (key.includes('${mode}')) {
        for (const mode of PREP_MODES) keys.add(key.replace('${mode}', mode))
      } else {
        keys.add(key)
      }
    }
  }
  return [...keys].sort()
}

test('resolution and refresh follow-client segments use the short existing label, not raw $tp keys', () => {
  assert.ok(script.includes("t('apps.display_profile_follow_client')"))
  assert.equal(script.includes("$tp('config.resolution_change_automatic')"), false)
  assert.equal(script.includes("$tp('config.refresh_rate_change_automatic')"), false)
  assert.equal(script.includes('$tp('), false)
})

test('every display-profile editor i18n key exists in all locales', () => {
  const keys = displayEditorKeys()
  assert.ok(keys.includes('apps.display_profile_follow_client'))
  assert.ok(keys.includes('config.display_device_prep_ensure_primary_desc_windows'))
  const locales = readdirSync(LOCALE_DIR).filter((name) => name.endsWith('.json')).sort()
  assert.equal(locales.length, 20)
  const missing = []
  for (const file of locales) {
    const catalog = flattenMessages(JSON.parse(readFileSync(new URL(file, LOCALE_DIR), 'utf8')))
    for (const key of keys) {
      if (!(key in catalog) || catalog[key] === '' || catalog[key] === key) {
        missing.push(`${file}: ${key}`)
      }
    }
  }
  assert.deepEqual(missing, [])
})
