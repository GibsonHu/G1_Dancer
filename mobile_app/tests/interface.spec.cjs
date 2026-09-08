const { test, expect } = require('@playwright/test');
for (const [name, width, height] of [['desktop',1440,1000],['phone',390,844]]) {
  test(name+' library and playback', async ({page}) => {
    await page.setViewportSize({width,height});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('/?demo');
    await expect(page.locator('.tile')).toHaveCount(6);
    await page.getByRole('button',{name:'Select Electric soul',exact:true}).click();
    await page.getByRole('button',{name:'Start dance',exact:true}).click();
    await page.locator('#confirm-action').click();
    await page.getByRole('button',{name:'Pause dance',exact:true}).click();
    await expect(page.getByRole('button',{name:'Resume dance',exact:true})).toBeEnabled();
    await page.locator('#stop').click();
    await page.locator('#menu').click();
    await expect(page.locator('#settings-dialog')).toBeVisible();
    await page.locator('#settings-dialog .close').click();
    await page.locator('#search').fill('Neon');
    await expect(page.locator('.tile')).toHaveCount(1);
    await page.locator('#search').fill('');
    await page.screenshot({path:'test-results/'+name+'.png',fullPage:true});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    expect(errors).toEqual([]);
  });
}
test('real API: upload song and cover, dance request', async ({page})=>{
  await page.goto('/');
  await expect(page.locator('.tile')).toHaveCount(2);
  const connect=page.locator('[data-connect-robot]:visible');
  if(await connect.isEnabled())await connect.click();
  await expect(page.locator('[data-robot-status]:visible')).toContainText('Robot online');
  await page.locator('#edit').click();
  await page.locator('#song-file').setInputFiles({name:'My track.mp3',mimeType:'audio/mpeg',buffer:Buffer.from('ID3test-data')});
  await expect(page.locator('#track-dialog')).not.toBeVisible();
  await expect(page.locator('#now-title')).toHaveText('My track');
  await page.locator('#edit').click();
  await page.locator('#cover-file').setInputFiles('../desktop_app/assets/app_icon.png');
  await expect(page.locator('#track-dialog')).not.toBeVisible();
  const response = page.waitForResponse(r=>r.url().endsWith('/play') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Start dance',exact:true}).click();
  await page.locator('#confirm-action').click();
  expect((await response).status()).toBe(202);
  await expect(page.getByRole('button',{name:'Pause dance',exact:true})).toBeEnabled();
  await page.locator('#stop').click();
});
