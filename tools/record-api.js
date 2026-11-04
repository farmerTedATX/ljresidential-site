const { chromium } = require('playwright');
const fs = require('fs');
const pages = ['contactinfo','qr-contact','neighborhoods','neighborhoods/northwest-hills','neighborhoods/westover-hills','', 'about','services','testimonials','home-valuation','terms-and-conditions','sitemap','dmca-notice','properties',
 'properties/2419-ashley-way-austin-tx-us-78744-7254772','properties/4207-canyonside-trail',
 'properties/4405-tambre-bnd-austin-tx-78738-8821382','properties/9705-mountain-quail-rd-austin-tx-78758-9452890'];
(async () => {
  const b = await chromium.launch(); const rec = [];
  const pg = await b.newPage({viewport:{width:1440,height:900}});
  pg.on('response', async r => {
    const u = new URL(r.url()); const t = r.request().resourceType();
    if (u.hostname.endsWith('ljresidentialgroup.com') && (t==='xhr'||t==='fetch')) {
      let body=''; try { body = await r.text(); } catch(e){}
      rec.push({page: pg.url(), method: r.request().method(), path: u.pathname + u.search, req: r.request().postData()||'', status: r.status(), ct: r.headers()['content-type']||'', body});
    }
  });
  for (const p of pages) {
    try { await pg.goto('https://ljresidentialgroup.com/'+p, {waitUntil:'networkidle', timeout:90000}); } catch(e){}
    for (let y=0;y<25;y++){ await pg.mouse.wheel(0,700); await pg.waitForTimeout(150); }
    await pg.waitForTimeout(1500);
  }
  fs.writeFileSync(process.argv[2], JSON.stringify(rec,null,1));
  for (const r of rec) console.log(r.status, r.method, r.path.slice(0,60), r.req.slice(0,90).replace(/\s+/g,' '), r.body.length);
  await b.close();
})();
