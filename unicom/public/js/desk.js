/* UniCom's Desk inbox deliberately uses the same permission-filtered API as the app. */
(() => {
  function mount() {
    if (document.getElementById('unicom-desk-launcher')) return
    const el = (tag, className, text) => {
      const node = document.createElement(tag)
      if (className) node.className = className
      if (text !== undefined) node.textContent = text
      return node
    }
    const button = (text, className = 'btn btn-default btn-sm') => {
      const node = el('button', className, text)
      node.type = 'button'
      return node
    }
    const launcher = button('UniCom', 'btn btn-primary unicom-desk-launcher')
    launcher.id = 'unicom-desk-launcher'
    launcher.setAttribute('aria-expanded', 'false')
    launcher.setAttribute('aria-controls', 'unicom-desk-panel')
    launcher.setAttribute('aria-label', 'Open UniCom issues')
    const panel = el('section', 'unicom-desk-panel')
    panel.id = 'unicom-desk-panel'
    panel.setAttribute('aria-label', 'UniCom issues')
    panel.hidden = true
    const header = el('header', 'unicom-desk-header')
    const heading = el('strong', '', 'UniCom issues')
    const refresh = button('Refresh')
    refresh.setAttribute('aria-label', 'Refresh issues')
    const close = button('Close')
    header.append(heading, refresh, close)
    const filters = el('div', 'unicom-desk-filters')
    const search = el('input', 'form-control input-sm')
    search.type = 'search'
    search.placeholder = 'Search issue titles'
    search.setAttribute('aria-label', 'Search issue titles')
    const view = el('select', 'form-control input-sm')
    view.setAttribute('aria-label', 'Issue view')
    for (const [value, label] of [['all', 'All accessible'], ['mine', 'My issues'], ['overdue', 'Overdue']]) {
      const option = el('option', '', label)
      option.value = value
      view.append(option)
    }
    filters.append(search, view)
    const status = el('div', 'unicom-desk-status')
    status.setAttribute('role', 'status')
    status.setAttribute('aria-live', 'polite')
    const list = el('div', 'unicom-desk-list')
    const footer = el('footer', 'unicom-desk-footer')
    const open = el('a', '', 'Open UniCom')
    open.href = '/unicom'
    const more = button('Load more')
    more.hidden = true
    const retry = button('Retry')
    retry.hidden = true
    footer.append(open, retry, more)
    panel.append(header, filters, status, list, footer)
    document.body.append(launcher, panel)
    const pageSize = 20
    let offset = 0
    let generation = 0
    let timer
    let loading = false
    let canLoadMore = false
    let retryAppend = false
    function renderRow(row) {
      const link = el('a', 'unicom-desk-issue')
      link.href = '/unicom/' + encodeURIComponent(row.name)
      const title = el('span', 'unicom-desk-title', row.title || 'Untitled issue')
      const meta = el('span', 'unicom-desk-meta')
      const details = [row.issue_id || row.name, row.status]
      if (row.next_action_date) details.push((row.overdue ? 'Overdue · ' : 'Due · ') + row.next_action_date)
      meta.textContent = details.filter(Boolean).join(' · ')
      link.append(title, meta)
      list.append(link)
    }
    async function load(append = false) {
      const request = ++generation
      const start = append ? offset : 0
      if (!append) { list.replaceChildren(); offset = 0 }
      loading = true
      retryAppend = append
      retry.hidden = true
      more.hidden = true
      status.textContent = 'Loading issues…'
      refresh.disabled = true
      try {
        const params = new URLSearchParams({ view: view.value, search: search.value.trim(), start: String(start), page_length: String(pageSize) })
        const response = await fetch('/api/method/unicom.api.list_issues?' + params, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        if (!response.ok) throw new Error('Request failed')
        const result = await response.json()
        if (request !== generation || panel.hidden) return
        if (!Array.isArray(result.message)) throw new Error('Invalid response')
        result.message.forEach(renderRow)
        offset = start + result.message.length
        canLoadMore = result.message.length === pageSize
        status.textContent = offset ? '' : 'No issues found.'
        more.hidden = !canLoadMore
      } catch (_) {
        if (request !== generation || panel.hidden) return
        status.textContent = 'Could not load issues. Please try again.'
        retry.hidden = false
      } finally {
        if (request === generation) { loading = false; refresh.disabled = false }
      }
    }
    function show() {
      panel.hidden = false
      launcher.setAttribute('aria-expanded', 'true')
      launcher.setAttribute('aria-label', 'Close UniCom issues')
      load()
    }
    function hide() {
      ++generation
      clearTimeout(timer)
      panel.hidden = true
      launcher.setAttribute('aria-expanded', 'false')
      launcher.setAttribute('aria-label', 'Open UniCom issues')
      list.replaceChildren()
      status.textContent = ''
      loading = false
      refresh.disabled = false
    }
    launcher.addEventListener('click', () => panel.hidden ? show() : hide())
    close.addEventListener('click', () => { hide(); launcher.focus() })
    panel.addEventListener('keydown', event => {
      if (event.key === 'Escape') { hide(); launcher.focus() }
    })
    refresh.addEventListener('click', () => load())
    retry.addEventListener('click', () => load(retryAppend))
    more.addEventListener('click', () => { if (!loading && canLoadMore) load(true) })
    view.addEventListener('change', () => load())
    search.addEventListener('input', () => { ++generation; clearTimeout(timer); timer = setTimeout(() => load(), 250) })
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true })
  else mount()
})()
