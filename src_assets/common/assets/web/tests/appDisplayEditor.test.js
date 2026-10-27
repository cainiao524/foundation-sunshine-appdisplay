import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { createRenderer, createSSRApp, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

// Compile the actual editor and shared display controls without a browser.
// Cover selection and command dragging are outside these display-policy tests.
const hooks = registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.endsWith('/AppEditor.vue') && ['./CommandTable.vue', './ImageSelector.vue'].includes(specifier)) {
      return { url: 'data:text/javascript,export default {render:()=>null}', shortCircuit: true }
    }
    if (specifier.startsWith('.') && context.parentURL && existsSync(new URL(`${specifier}.js`, context.parentURL))) {
      return next(`${specifier}.js`, context)
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (!url.endsWith('.vue')) return next(url, context)
    const filename = fileURLToPath(url)
    const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
    const script = compileScript(descriptor, { id: filename, genDefaultAs: 'component' })
    const template = compileTemplate({
      source: descriptor.template.content, filename, id: filename,
      ssr: true, ssrCssVars: descriptor.cssVars,
      compilerOptions: { bindingMetadata: script.bindings },
    })
    assert.deepEqual(template.errors, [])
    return {
      format: 'module', shortCircuit: true,
      source: `${script.content}\n${template.code}\ncomponent.ssrRender = ssrRender; export default component;`,
    }
  },
})
let AppEditor, DisplayPreparationPicker
try {
  AppEditor = (await import('../components/AppEditor.vue')).default
  DisplayPreparationPicker = (await import('../configs/tabs/audiovideo/DisplayPreparationPicker.vue')).default
} finally {
  hooks.deregister()
}

const messages = JSON.parse(readFileSync(new URL('../public/assets/locale/en.json', import.meta.url), 'utf8'))
function localize(app) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: messages } })
  app.use(i18n)
  app.provide('platform', { value: 'windows' })
  app.provide('i18n', i18n.global)
  app.provide('platformMessage', {
    getMessageUsingPlatform: (key) => i18n.global.t(i18n.global.te(`${key}_windows`) ? `${key}_windows` : key),
  })
  return app
}

const appData = (overrides = {}) => ({ name: 'Display test', 'display-target': 'virtual', ...overrides })
const renderEditor = (overrides) => renderToString(localize(createSSRApp(AppEditor, { platform: 'windows', app: appData(overrides) })))
const radios = (html, name) => [...html.matchAll(/<input\b[^>]*>/g)].map(([input]) => input).filter((input) => input.includes(`name="${name}"`))

async function mountEditor(t, overrides) {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ display_devices: [] })))
  let state
  const saved = []
  // Mount the real setup/watchers with an empty host; SSR tests cover markup.
  const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
  const app = localize(renderer.createApp({
    ...AppEditor,
    setup(props, context) {
      state = AppEditor.setup(props, context)
      return () => null
    },
  }, { platform: 'windows', app: appData(overrides), onSaveApp: (value) => saved.push(value) }))
  app.mount({})
  t.after(() => app.unmount())
  await nextTick()
  return { state, saved }
}

test('fixed host values render their values without claiming to follow the client', async () => {
  const html = await renderEditor({
    'display-resolution': '2560x1440', 'display-refresh-rate': '59.94',
    'display-resolution-mode': 'no_operation', 'display-refresh-rate-mode': '',
  })
  assert.ok(html.includes('Fixed at 2560x1440; overrides the policy above.'))
  assert.ok(html.includes('Fixed at 59.94 Hz; overrides the policy above.'))
  assert.ok(!html.includes(messages.apps.display_profile_resolution_follow_hint))
  assert.ok(!html.includes(messages.apps.display_profile_refresh_rate_follow_hint))
  assert.match(radios(html, 'app_resolution_change').find((input) => input.includes(' checked')), /value="no_operation"/)
  assert.match(radios(html, 'app_refresh_rate_change').find((input) => input.includes(' checked')), /value="inherit"/)
})

test('fixing only one dimension leaves the other client policy active', async () => {
  const html = await renderEditor({ 'display-resolution': '1920x1080', 'display-refresh-rate-mode': 'client' })
  assert.ok(html.includes('Fixed at 1920x1080; overrides the policy above.'))
  assert.ok(html.includes(messages.apps.display_profile_refresh_rate_follow_hint))
  assert.ok(radios(html, 'app_resolution_change').every((input) => input.includes(' disabled')))
  assert.ok(radios(html, 'app_refresh_rate_change').every((input) => !input.includes(' disabled')))
})

test('clearing fixed values restores the saved policies and preserves other display settings', async (t) => {
  const { state, saved } = await mountEditor(t, {
    'display-target': 'physical', 'display-output-name': 'physical-monitor',
    'display-resolution': '2560x1440', 'display-refresh-rate': '59.94',
    'display-resolution-mode': 'no_operation', 'display-refresh-rate-mode': 'client',
    'display-hdr': 'off', 'display-disconnect-action': 'restore', 'display-dynamic-resolution-follow-display': 'disabled',
  })
  assert.equal(state.fixedValuesEnabled.value, true)
  await state.saveApp()
  assert.equal(saved[0]['display-refresh-rate'], '59.94')
  state.fixedValuesEnabled.value = false
  await nextTick()
  await state.saveApp()
  assert.deepEqual(saved[1], { ...saved[0], 'display-resolution': '', 'display-refresh-rate': '' })
  assert.equal(state.resHintText.value, messages.apps.display_profile_resolution_ignore_hint)
  assert.equal(state.rrHintText.value, messages.apps.display_profile_refresh_rate_follow_hint)
})

test('switching apps reinitializes fixed controls without discarding saved values', async (t) => {
  const { state, saved } = await mountEditor(t, { 'display-resolution': '2560x1440' })
  state.initializeForm(appData())
  await nextTick()
  assert.equal(state.fixedValuesEnabled.value, false)
  state.initializeForm(appData({ 'display-refresh-rate': '119.88', 'display-refresh-rate-mode': 'no_operation' }))
  await nextTick()
  assert.equal(state.fixedValuesEnabled.value, true)
  assert.equal(state.hasFixedResolution.value, false)
  assert.equal(state.appRefreshRateRule.value, 'no_operation')
  assert.match(state.rrHintText.value, /119\.88 Hz/)
  await state.saveApp()
  assert.equal(saved[0]['display-refresh-rate'], '119.88')
})

test('missing or empty app topology stays inherited on render and save', async (t) => {
  for (const overrides of [{}, { 'display-device-prep': '' }]) {
    const html = await renderEditor(overrides)
    const choices = radios(html, 'app_display_device_prep')
    assert.equal(choices.length, 6)
    assert.match(choices.find((input) => input.includes(' checked')), /value=""/)
  }
  const { state, saved } = await mountEditor(t, {})
  await state.saveApp()
  assert.equal(saved[0]['display-device-prep'], '')
  for (const mode of ['no_operation', 'ensure_active', 'ensure_primary', 'ensure_secondary', 'ensure_only_display']) {
    state.initializeForm(appData({ 'display-device-prep': mode }))
    await nextTick()
    await state.saveApp()
    assert.equal(saved.at(-1)['display-device-prep'], mode)
    state.formData.value['display-device-prep'] = ''
    await state.saveApp()
    assert.equal(saved.at(-1)['display-device-prep'], '')
  }
})

test('the global topology picker still offers only its five explicit policies', async () => {
  const html = await renderToString(localize(createSSRApp(DisplayPreparationPicker, { modelValue: 'ensure_primary' })))
  const choices = radios(html, 'display_device_prep')
  assert.equal(choices.length, 5)
  assert.match(choices.find((input) => input.includes(' checked')), /value="ensure_primary"/)
})
