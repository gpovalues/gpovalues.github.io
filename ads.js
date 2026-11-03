(function () {
  'use strict';
  if (window.GPO_CONFIG?.adsEnabled !== true) return;
  const load = () => {
    window.yaContextCb = window.yaContextCb || [];
    window.yaContextCb.push(() => {
      if (window.matchMedia('(min-width: 900px)').matches) {
        window.Ya.Context.AdvManager.render({ blockId: 'R-A-20264146-12', type: 'floorAd', platform: 'desktop' });
      }
    });
    const context = document.createElement('script');
    context.src = 'https://yandex.ru/ads/system/context.js';
    context.async = true;
    document.head.appendChild(context);
    const placement = document.createElement('script');
    placement.dataset.pageId = '20264146';
    placement.src = 'https://yandex.ru/ads/system/ap-loader.js';
    placement.async = true;
    document.head.appendChild(placement);
  };
  window.addEventListener('load', () => {
    if (window.requestIdleCallback) window.requestIdleCallback(load, { timeout: 8000 });
    else window.setTimeout(load, 4000);
  }, { once: true });
})();
