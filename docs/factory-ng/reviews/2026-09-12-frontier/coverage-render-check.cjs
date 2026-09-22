const fs=require('fs'), vm=require('vm'), assert=require('assert');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',clientWidth:400,clientHeight:200,style:{setProperty(){}},addEventListener(){},appendChild(){},classList:{add(){},remove(){}}});return elements.get(id)}
const data=JSON.parse(fs.readFileSync('/opt/development/magic-ops/state/factory-ng-coverage.json'));
const context={document:{getElementById:el,querySelector:el,createElement:()=>el(Math.random()),querySelectorAll:()=>[]},window:{addEventListener(){}},fetch:async()=>({json:async()=>data}),setInterval(){},setTimeout,clearTimeout,requestAnimationFrame:f=>f(),console,Date,Map,Set};
const html=fs.readFileSync('/opt/development/magic-ops/services/dispatcher/v4/coverage.html','utf8');
vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],context);
setTimeout(()=>{assert(el('meta-line').textContent.includes(data.measured_at));assert(el('meta-line').textContent.includes(data.source_revision.slice(0,12)));assert(el('stat-row').innerHTML.includes('Measured one-miss candidates'));assert(el('headline-callout').textContent.includes('Runnable supply'));assert(el('zones').innerHTML.includes('Has completed work'));assert(!el('stamp').innerHTML.includes('data unavailable'));console.log('Coverage rendering, measurement provenance and historical labels passed.');},10);
