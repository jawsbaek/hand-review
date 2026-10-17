import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const artifact = path.resolve(process.argv[2] || "reports/demo.html");
const stateCaptures=process.env.COACHING_SCREENSHOTS;
if(stateCaptures) await mkdir(stateCaptures,{recursive:true});
const browser = await chromium.launch({headless:true,args:process.platform==="darwin"?["--single-process","--in-process-gpu","--disable-gpu"]:[]});
let child;
try {
  const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
  const errors=[], external=[];
  page.on("pageerror", error=>errors.push(error.message));
  await page.route("**/*", route=>{
    const url=route.request().url();
    if(url===pathToFileURL(artifact).href||url.startsWith("http://127.0.0.1:")) return route.continue();
    external.push(url);return route.abort();
  });
  await page.goto(pathToFileURL(artifact).href);
  const data=JSON.parse(await page.locator("#report-data").textContent());
  const ready=data.hands.flatMap((h,hi)=>h.decisions.map((d,di)=>({hi,di,d}))).find(x=>x.d.analysis?.status==="ready");
  assert.ok(ready,"No calculated recommendation in artifact");
  await page.evaluate(({hi,di})=>chooseHand(hi,di),ready);
  assert.equal(await page.locator("#action-comparison .comparison-line").count(),2);
  assert.ok((await page.locator("#action-comparison").textContent()).includes("모델 추정"));
  if(ready.d.analysis.coaching.basis==="model_baseline") {
    assert.ok((await page.locator('[data-method="model_baseline"]').textContent()).includes("이후 체크다운"));
    assert.ok((await page.locator('[data-method="model_baseline"]').textContent()).includes("레이크 0"));
  }
  await page.locator("#action-comparison details").first().locator("summary").click();
  await page.locator("#coaching-scenario").selectOption("sticky");
  assert.ok((await page.locator("#scenario-result").textContent()).includes("가정 실험"));
  await page.locator("#action-comparison details").last().locator("summary").click();
  assert.equal(await page.locator(".range-row textarea").first().getAttribute("readonly"),"");
  // Exercise async client recovery without opening a listener. The real HTTP
  // calculation below separately verifies backend results and range sensitivity.
  const opponent=Object.keys(ready.d.analysis.model.ranges).find(s=>Number(s)!==data.hands[ready.hi].hero.seat);
  assert.ok(opponent);
  await page.evaluate(()=>{
    window.clientTest={base:structuredClone(currentDecision().analysis),fetch:window.fetch,hold:true,mode:"success"};
    report.analysis.live_token="synthetic-client-state-test";
    window.fetch=async(url,options)=>{
      const test=window.clientTest;
      if(url==="/api/analyze") {
        test.ranges=JSON.parse(options.body).ranges;
        if(test.hold) await new Promise(resolve=>{test.release=resolve;});
        if(test.mode==="error") return new Response(JSON.stringify({error:"레인지 입력을 확인하고 다시 계산하세요."}),{status:400});
        return new Response(JSON.stringify({job:"synthetic-client-job"}),{status:202});
      }
      const analysis=test.mode==="unavailable"
        ? {status:"unavailable",note:"내 레인지에 현재 내 카드 조합을 포함하세요.",model:{status:"unavailable"},solver:{status:"unavailable"}}
        : {...structuredClone(test.base),model:{...structuredClone(test.base.model),ranges:test.ranges}};
      return new Response(JSON.stringify({status:"complete",analysis}));
    };
    renderDecision();
  });
  await page.locator("#range-details").evaluate(n=>{n.open=true;});
  const editor=page.locator('textarea[data-seat="'+opponent+'"]');
  await editor.fill("AA");
  assert.equal(await page.locator("#range-stale").isVisible(),true);
  if(stateCaptures) await page.screenshot({path:path.join(stateCaptures,"range-draft-desktop.png"),fullPage:true});
  await page.locator("#range-submit").click();
  await page.evaluate(()=>renderDecision());
  assert.ok((await page.locator("#analysis-status").textContent()).includes("계산하고"));
  assert.equal(await page.locator("#range-submit").isDisabled(),true);
  await editor.fill("KK");
  await page.evaluate(()=>{clientTest.hold=false;clientTest.release();});
  await page.waitForFunction(()=>document.getElementById("analysis-status").textContent.includes("완료"));
  assert.equal(await editor.inputValue(),"KK","An in-flight result overwrote the newer draft");
  assert.equal(await page.locator("#range-stale").isVisible(),true);
  assert.equal(await editor.evaluate(n=>n===document.activeElement),true);
  assert.equal(await page.locator("#range-details").evaluate(n=>n.open),true);
  await editor.fill("AA");
  assert.equal(await page.locator("#range-stale").isVisible(),false);
  await page.locator("#range-submit").click();
  await page.waitForFunction(()=>!document.getElementById("range-submit").disabled);
  assert.equal(await page.locator("#range-submit").evaluate(n=>n===document.activeElement),true);
  await page.evaluate(()=>{clientTest.mode="unavailable";});
  await page.locator("#range-submit").click();
  await page.waitForFunction(()=>currentDecision().analysis.status==="unavailable");
  await page.evaluate(()=>{clientTest.mode="error";});
  await editor.fill("AA:NaN");
  await page.locator("#range-submit").focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(()=>document.getElementById("analysis-status").textContent.includes("입력을 확인"));
  assert.equal(await page.evaluate(()=>currentDecision().analysis.status),"unavailable");
  assert.equal(await page.locator("#range-details").evaluate(n=>n.open),true);
  assert.equal(await page.locator("#range-submit").evaluate(n=>n===document.activeElement),true);
  if(stateCaptures) {
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(stateCaptures,"range-error-mobile.png"),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
  }
  await page.evaluate(()=>{clientTest.mode="success";});
  await editor.fill("AA");
  await page.locator("#range-submit").click();
  await page.waitForFunction(()=>currentDecision().analysis.status==="ready");
  await page.evaluate(()=>{
    currentDecision().analysis=clientTest.base;window.fetch=clientTest.fetch;delete report.analysis.live_token;
    rangeDrafts.clear();rangeStates.clear();analysisRevisions.clear();renderDecision();
  });
  await page.locator("#mode").selectOption("practice");
  await page.evaluate(({hi,di})=>chooseHand(hi,di),ready);
  assert.equal(await page.locator("#action-comparison").count(),0,"Practice leaks recommendation before choice");
  await page.locator(".practice-buttons button").first().click();
  assert.equal(await page.locator("#action-comparison").count(),1);
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  let live="skipped: workspace listener permission";
  if(!process.env.SKIP_LIVE_WORKBENCH) {
    let output="";
    child=spawn(process.env.HAND_REVIEW_PYTHON||"python",["-m","hand_review.analyze","serve","samples/pokerist/demo.jsonl","--port","0","--analysis-samples","32","--no-solver"],{stdio:["ignore","pipe","pipe"]});
    child.stdout.on("data", chunk=>{output+=chunk;});
    child.stderr.on("data", chunk=>{output+=chunk;});
    const deadline=Date.now()+20000;
    while(!/http:\/\/127\.0\.0\.1:\d+\//.test(output)&&Date.now()<deadline&&child.exitCode===null) await new Promise(r=>setTimeout(r,100));
    const url=output.match(/http:\/\/127\.0\.0\.1:\d+\//)?.[0];
    assert.ok(url,"Workbench did not start: "+output);
    await page.goto(url);
    await page.getByRole("button",{name:/^전체 /}).click();
    await page.evaluate(()=>chooseHand(0,0));
    await page.waitForFunction(()=>report.hands[0].decisions[0].analysis?.status==="ready",null,{timeout:60000});
    const before=await page.evaluate(()=>report.hands[0].decisions[0].analysis.model.actions);
    await page.locator("#range-details").evaluate(n=>{n.open=true;});
    await page.locator('textarea[data-seat="1"]').fill("AA");
    await page.getByRole("button",{name:"이 레인지로 다시 계산"}).click();
    await page.waitForFunction(()=>report.hands[0].decisions[0].analysis?.model?.ranges?.["1"]==="AA",null,{timeout:60000});
    const after=await page.evaluate(()=>report.hands[0].decisions[0].analysis.model.actions);
    assert.notDeepEqual(before,after,"Range change did not alter computed EVs");
    assert.ok((await page.locator("#analysis-status").textContent()).includes("완료"));
    // Invalid input is recoverable and cannot replace the last valid analysis.
    assert.equal(await page.locator("#range-details").evaluate(n=>n.open),true);
    assert.equal(await page.locator("#range-submit").evaluate(n=>n===document.activeElement),true);
    await page.locator('textarea[data-seat="1"]').fill("AA:NaN");
    assert.equal(await page.locator("#range-stale").isVisible(),true);
    await page.getByRole("button",{name:"이 레인지로 다시 계산"}).click();
    await page.waitForFunction(()=>document.getElementById("analysis-status").textContent.includes("0~1"));
    assert.deepEqual(await page.evaluate(()=>report.hands[0].decisions[0].analysis.model.actions),after);
    live="passed: real loopback API and range recomputation";
  }
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  process.stdout.write(JSON.stringify({static:"passed",live,pageErrors:errors,externalRequests:external})+"\n");
} finally {
  if(child&&child.exitCode===null) child.kill("SIGTERM");
  await browser.close();
}
