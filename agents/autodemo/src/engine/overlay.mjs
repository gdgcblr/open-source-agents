// The caption/title overlay, injected into the page under test.
//
// It is a single fixed-position div with `pointer-events:none`, so it can sit
// on top of any app without intercepting the clicks the walkthrough makes.
// Re-injected after every navigation, because a page load wipes it.

export const OVERLAY_ID = 'autodemo-overlay-root'

/** Install the overlay (idempotent) and set its current state. */
export async function setStage(page, { mode, title = '', subtitle = '', theme }) {
  await page.evaluate(({ mode, title, subtitle, theme, ROOT_ID }) => {
    let root = document.getElementById(ROOT_ID)
    if (!root) {
      root = document.createElement('div')
      root.id = ROOT_ID
      root.style.cssText =
        `position:fixed;inset:0;z-index:2147483000;pointer-events:none;font-family:${theme.font};`
      const capPos = theme.position === 'top' ? 'top:40px;' : 'bottom:40px;'
      root.innerHTML = `
        <div id="ad-title" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:radial-gradient(ellipse at center,rgba(6,14,28,.72),rgba(3,7,18,.94));opacity:0;transition:opacity .6s ease;">
          <div id="ad-eyebrow" style="font-size:12px;letter-spacing:3px;color:${theme.accent};text-transform:uppercase;"></div>
          <div id="ad-title-main" style="font-size:52px;font-weight:800;color:#fff;text-align:center;max-width:74%;line-height:1.12;"></div>
          <div id="ad-title-sub" style="font-size:20px;color:#cbd5e1;text-align:center;max-width:64%;"></div>
        </div>
        <div id="ad-cap" style="position:absolute;left:50%;${capPos}transform:translateX(-50%);max-width:76%;padding:14px 24px;border-radius:14px;background:rgba(3,7,18,.82);box-shadow:0 10px 44px rgba(0,0,0,.5);border:1px solid rgba(148,163,184,.25);opacity:0;transition:opacity .45s ease;text-align:center;">
          <div id="ad-cap-main" style="font-size:22px;font-weight:700;color:#fff;"></div>
          <div id="ad-cap-sub" style="font-size:14px;color:${theme.accent};margin-top:3px;"></div>
        </div>`
      document.body.appendChild(root)
    }
    const q = id => root.querySelector('#' + id)
    q('ad-eyebrow').textContent = theme.eyebrow || ''
    const titleCard = q('ad-title'), cap = q('ad-cap')
    if (mode === 'title') {
      q('ad-title-main').textContent = title
      q('ad-title-sub').textContent = subtitle
      titleCard.style.opacity = '1'; cap.style.opacity = '0'
    } else if (mode === 'caption') {
      q('ad-cap-main').textContent = title
      q('ad-cap-sub').textContent = subtitle
      titleCard.style.opacity = '0'; cap.style.opacity = '1'
    } else {
      titleCard.style.opacity = '0'; cap.style.opacity = '0'
    }
  }, { mode, title, subtitle, theme, ROOT_ID: OVERLAY_ID })
}
