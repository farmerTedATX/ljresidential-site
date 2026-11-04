const { chromium } = require('playwright');
const OUT = process.argv[2], BASE = process.argv[3];
const pages = ['contactinfo/','qr-contact/','neighborhoods/','neighborhoods/northwest-hills/','neighborhoods/westover-hills/','', 'about/','services/','testimonials/','home-valuation/','terms-and-conditions/','sitemap/','dmca-notice/','properties/',
 'properties/2419-ashley-way-austin-tx-us-78744-7254772/','properties/4207-canyonside-trail/',
 'properties/4405-tambre-bnd-austin-tx-78738-8821382/','properties/9705-mountain-quail-rd-austin-tx-78758-9452890/'];
(async () => {
  const b = await chromium.launch();
  for (const [w,h,tag] of [[1440,900,'desktop'],[390,844,'mobile']]) {
    const ctx = await b.newContext({ viewport:{width:w,height:h} });
    const pg = await ctx.newPage();
    const ext = new Set(), bad = new Set(), errs = new Set();
    pg.on('request', r => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('data:') && !u.startsWith('blob:')) ext.add(u.slice(0,140)); });
    pg.on('response', r => { if (r.status() >= 400) bad.add(r.status()+' '+r.url().slice(0,140)); });
    pg.on('pageerror', e => errs.add(String(e).slice(0,200)));
    for (const p of pages) {
      try { await pg.goto(BASE + p, {waitUntil:'networkidle', timeout:60000}); } catch(e) { console.log('timeout', p); }
      for (let y=0; y<30; y++) { await pg.mouse.wheel(0,700); await pg.waitForTimeout(150); }
      await pg.waitForTimeout(1500);
      await pg.evaluate(()=>window.scrollTo(0,0)); await pg.waitForTimeout(800);
      const name = (p.replace(/\/$/,'')||'index').replace(/\//g,'_');
      await pg.screenshot({path: `${OUT}/${name}.${tag}.png`, fullPage:true});
    }
    console.log(`[${tag}] external:`, [...ext]); console.log(`[${tag}] errors>=400:`, [...bad]); console.log(`[${tag}] js errors:`, [...errs]);
    await ctx.close();
  }
  await b.close();
})();
