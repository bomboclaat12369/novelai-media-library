// The same collectible face is used for a Set preview and an earned After Hours form.
(() => {
  'use strict';
  const root = document.getElementById('nai-media-host')?.shadowRoot;
  const assets = typeof naiCardEditionAssets === 'undefined' ? null : naiCardEditionAssets.evolution;
  if (!root?.naiCards || !assets) return;

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = (tag, attributes) => {
    const element = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    return element;
  };

  function stations(current, total) {
    if (total <= 8) return Array.from({length: total}, (_, i) => i + 1);
    const near = new Set([1, total, current - 1, current, current + 1].filter(n => n >= 1 && n <= total));
    if (current <= 3) near.add(2);
    if (current >= total - 2) near.add(total - 1);
    const labels = [];
    for (const n of [...near].sort((a, b) => a - b)) {
      const gap = n - labels.at(-1);
      if (gap === 2) labels.push(n - 1);
      if (gap > 2) labels.push(null);
      labels.push(n);
    }
    return labels;
  }

  function diamond(x, y, rx, ry, fill) {
    return svg('path', {d: `M${x-rx} ${y}l${rx} ${-ry} ${rx} ${ry} ${-rx} ${ry}z`, fill});
  }

  const measure = document.createElement('canvas').getContext('2d');
  function number(parent, value, x, y, size, fill, maxWidth, italic = false) {
    const family = italic ? '"Palatino Linotype", Palatino, "Book Antiqua", serif' : '"Times New Roman", Times, serif';
    const style = italic ? 'italic' : 'normal';
    const text = svg('text', {x, y, fill, 'text-anchor':'middle', 'dominant-baseline':'central',
      'font-size':size, 'font-family':family, 'font-style':style});
    let inkWidth = size / 2;
    if (measure) {
      measure.font = `${style} ${size}px ${family}`;
      let metrics = measure.measureText(value);
      if (metrics.width > maxWidth) {
        size *= maxWidth / metrics.width;
        measure.font = `${style} ${size}px ${family}`;
        metrics = measure.measureText(value);
        text.setAttribute('font-size', size);
      }
      inkWidth = metrics.actualBoundingBoxLeft + metrics.actualBoundingBoxRight;
      text.setAttribute('text-anchor', 'start');
      text.setAttribute('dominant-baseline', 'alphabetic');
      text.setAttribute('x', x + metrics.actualBoundingBoxLeft - inkWidth / 2);
      text.setAttribute('y', y + (metrics.actualBoundingBoxAscent - metrics.actualBoundingBoxDescent) / 2);
    }
    text.textContent = value;
    parent.append(text);
    return inkWidth;
  }

  function ticket(overlay, current, total) {
    const labels = stations(current, total);
    const pitch = Math.min(174, 586 / labels.length);
    const first = 402 - (labels.length - 1) * pitch / 2;
    const strip = svg('g', {transform: 'translate(0 1404)'});
    labels.forEach((n, i) => {
      const x = first + i * pitch;
      if (n === null) {
        for (const dx of [-7, 0, 7]) strip.append(svg('circle', {cx:x+dx, cy:50, r:1.8, fill:'#795b45'}));
        return;
      }
      const active = n === current;
      const radius = Math.min(33, pitch / 2 - 4);
      const mark = svg('g', {'data-form-number': n});
      if (active) {
        mark.setAttribute('data-current', '');
        const seal = svg('g', {transform:`translate(${x} 45) rotate(-3.1513)`});
        seal.append(svg('ellipse', {rx:radius+2, ry:31, fill:'#681d30'}),
          svg('ellipse', {rx:radius-1.7, ry:27.7, fill:'none', stroke:'#e2c496', 'stroke-width':1.15}));
        mark.append(seal);
      }
      const width = number(mark, String(n), x, 45, active ? 56 : 53,
        active ? '#f9e8c7' : n < current ? '#542234' : '#674c48', active ? 2*radius-12 : pitch-16);
      if (n < current) {
        const w = Math.max(11, Math.min(20, (width + 1) / 2));
        mark.append(svg('path', {d:`M${x-w} 72H${x-3}M${x+3} 72H${x+w}`, stroke:'#833746', 'stroke-width':1.7}),
          diamond(x, 72, 2.8, 2.5, '#833746'));
      }
      strip.append(mark);
      if (i < labels.length - 1 && labels.length <= 6) strip.append(diamond(x+pitch/2, 46, 2.5, 1.65, '#a37b57'));
    });
    number(strip, `${current}\u2009/\u2009${total}`, 852, 46, 57, '#522334', 173, true);
    overlay.append(strip);
  }

  const style = document.createElement('style');
  style.textContent = `
    .naiTradingCard.naiEncoreCard{position:relative;display:block;overflow:hidden;width:100%;aspect-ratio:7/10;box-sizing:border-box;isolation:isolate;padding:0;border:0;border-radius:0;background:#220d16}
    .naiEncoreCard>.naiCardPhotoWindow{position:absolute;left:10%;top:13%;width:80%;height:74.66666666666667%;margin:0;padding:0;overflow:hidden;border:0;border-radius:0;background:#160c11}
    .naiEncoreCard>.naiEncoreFrame,.naiEncoreCard>.naiEncorePrint{position:absolute;inset:0;width:100%;height:100%;max-height:none;max-width:none;margin:0;padding:0;border:0;border-radius:0;pointer-events:none}
  `;
  root.append(style);

  root.naiCards.evolutionCard = function(photo, name, frame, current, total) {
    if (!Number.isSafeInteger(total) || !Number.isSafeInteger(current) || current < 1 || current > total) {
      throw new RangeError('Invalid Evolution form.');
    }
    const card = document.createElement('div');
    card.className = 'naiTradingCard naiEncoreCard';
    const label = `${name} · Evolution · Form ${current} of ${total}`;
    card.setAttribute('role', 'img');
    card.setAttribute('aria-label', label);
    card.title = label;
    const aperture = document.createElement('div');
    aperture.className = 'naiCardPhotoWindow';
    aperture.append(photo);
    card.append(aperture);
    // Older manual crops were saved against the original card opening.
    photo.naiLegacyFramingReference = {left:.05, top:.038, width:.90, height:.84};
    root.naiCards.applyFrame(photo, frame);

    const art = document.createElement('img');
    art.className = 'naiEncoreFrame';
    art.alt = '';
    art.draggable = false;
    art.src = current === total ? assets.finale : assets.regular;
    const overlay = svg('svg', {class:'naiEncorePrint', viewBox:'0 0 1050 1500', 'aria-hidden':'true'});
    const actor = svg('text', {x:0, y:1357, 'text-anchor':'middle', 'dominant-baseline':'central',
      'font-family':'Candara, Optima, sans-serif', 'font-size':56, 'letter-spacing':6, fill:'#f4d49a',
      transform:'translate(525 0) scale(1.3 1)'});
    actor.textContent = name.toUpperCase();
    if (measure) {
      measure.font = '56px Candara, Optima, sans-serif';
      const width = measure.measureText(actor.textContent).width + 6 * Array.from(actor.textContent).length;
      actor.setAttribute('transform', `translate(525 0) scale(${Math.min(1.3, 756 / Math.max(1, width))} 1)`);
    }
    overlay.append(actor);
    ticket(overlay, current, total);
    card.append(art, overlay);
    return card;
  };
})();
