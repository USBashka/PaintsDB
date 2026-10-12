'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => n === null || n === undefined ? '—' : Number(n).toFixed(3);
const displayDate = s => s ? String(s).slice(0,10).split('-').reverse().join('.') : '—';
const displayTime = s => s ? new Date(s).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const title = r => r.name || `Рецепт ${r.id ?? ''}`;
const main = $('#main');
const state = {context:null,path:null,view:'recipes',period:'',today:'',sequence:0,query:'',color:'',filterMonth:'',costMode:'selected',recipeSort:'created_at',recipeDesc:true,componentSort:'code',componentDesc:false,selected:new Set(),recipes:[],components:[],editor:null,compareIds:[],historyMode:'per_kg',render:0};
window.dirty = false;
window.uiErrors = [];
window.addEventListener('error', e => window.uiErrors.push(e.message));
window.addEventListener('unhandledrejection', e => {window.uiErrors.push(String(e.reason)); notify(String(e.reason?.message || e.reason), true);});

async function api(operation, args = {}, context = state.context) {
  const response = await window.pywebview.api.request(operation, args, context);
  if (!response.ok) { const error = new Error(response.error.message); error.field = response.error.field; error.code = response.error.code; throw error; }
  return response.data;
}
function notify(message, error = false, action = null) {
  const box = $('#notice'); box.hidden = false; box.className = error ? 'error' : '';
  box.innerHTML = `<span>${esc(message)}</span>${action ? '<button id="notice-action">Открыть</button>' : ''}<button class="dismiss quiet" aria-label="Закрыть уведомление">×</button>`;
  $('.dismiss',box).onclick = () => box.hidden = true;
  if (action) $('#notice-action').onclick = action;
}
function status(message) { $('#status').textContent = message; }
function allowLeave() {
  if (window.dirty && !confirm('Изменения не сохранены. Продолжить без сохранения?')) return false;
  window.dirty = false; return true;
}
function beginEdit() { window.dirty = true; }
function setDatabase(s) {
  state.context=s.context; state.path=s.path; state.today=s.today; state.period ||= s.today.slice(0,7); state.sequence=s.sequence;
  $('#database-name').textContent=s.path ? s.path.split(/[\\/]/).pop() : 'База не открыта';
  $('#database-name').title=s.path || '';
  $$('.needs-db').forEach(b=>b.disabled=!state.context);
}
function showDialog(heading, body, buttons, wide=false) {
  const dialog=$('#dialog'); if(dialog.open) dialog.close(); dialog.className=wide?'import-dialog':'';
  $('#dialog-content').innerHTML=`<div class="dialog-head"><h2>${esc(heading)}</h2><button class="quiet icon" data-close aria-label="Закрыть">×</button></div><div class="dialog-body">${body}<div id="dialog-error" class="error-text" role="alert"></div></div><div class="dialog-foot">${buttons}</div>`;
  $$('[data-close]',dialog).forEach(b=>b.onclick=()=>{if(!window.dirty || confirm('Закрыть без сохранения изменений?')) {window.dirty=false;dialog.close();}});
  dialog.oncancel=e=>{if(window.dirty&&!confirm('Закрыть без сохранения изменений?')) e.preventDefault();else window.dirty=false;};
  dialog.showModal();
}
async function runForm(button, task) {
  button.disabled=true; $('#dialog-error') && ($('#dialog-error').textContent='');
  try { await task(); } catch(e) { const box=$('#dialog-error') || $('#editor-error'); if(box)box.textContent=e.message;else notify(e.message,true); } finally {button.disabled=false;}
}

async function fileAction(kind) {
  $('#file-menu').hidden=true;
  if(['create','open'].includes(kind)&&!allowLeave()) return;
  const expected=state.context;
  const path=await window.pywebview.api.choose_file(kind); if(!path)return;
  try {
    if(kind==='backup') {await api('backup_database',{path},expected);notify('Резервная копия сохранена');return;}
    const s=await api(kind==='create'?'create_database':'open_database',{path},expected);
    setDatabase(s);state.editor=null;state.selected.clear();state.compareIds=[];state.view='recipes';state.query='';await render();
  } catch(e){notify(e.message,true);}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-file]');if(b)fileAction(b.dataset.file);});
$('#file-button').onclick=()=>{const menu=$('#file-menu');menu.hidden=!menu.hidden;$('#file-button').setAttribute('aria-expanded',String(!menu.hidden));};
document.addEventListener('click',e=>{if(!e.target.closest('.file-menu'))$('#file-menu').hidden=true;});
$$('[data-view]').forEach(b=>b.onclick=async()=>{if(!allowLeave())return;state.view=b.dataset.view;state.editor=null;state.query='';await render();});
$('#mcp-button').onclick=async()=>{
  $('#file-menu').hidden=true;const s=await window.pywebview.api.mcp_settings();
  showDialog('Подключение MCP',`<div class="field"><label for="mcp-url">Адрес</label><input id="mcp-url" class="token" readonly value="${esc(s.url)}"></div><div class="field" style="margin-top:16px"><label for="mcp-token">Bearer-токен</label><input id="mcp-token" class="token" readonly value="${esc(s.token)}"></div>`,`<button data-close>Закрыть</button>`);
};

function sortHead(label,key,kind,numeric=false) {
  const current=state[kind+'Sort']===key;return `<th class="${numeric?'num':''}"><button data-sort="${key}">${esc(label)}${current?(state[kind+'Desc']?' ↓':' ↑'):''}</button></th>`;
}
function bindSort(kind) {
  $$('[data-sort]',main).forEach(b=>b.onclick=async()=>{const key=b.dataset.sort;if(state[kind+'Sort']===key)state[kind+'Desc']=!state[kind+'Desc'];else {state[kind+'Sort']=key;state[kind+'Desc']=false;}await render();});
}
let searchTimer;
function bindToolbar() {
  $('#query')?.addEventListener('input',e=>{state.query=e.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(()=>render(true),220);});
  $('#period')?.addEventListener('change',async e=>{if(e.target.value){state.period=e.target.value;await render();}});
}
async function render(restoreSearch=false) {
  const version=++state.render;
  $$('[data-view]').forEach(b=>b.classList.toggle('active',state.view===b.dataset.view));
  if(!state.context) {main.innerHTML='<div class="empty"><h1>PaintsDB</h1><div class="actions"><button class="primary" data-file="create">Создать базу</button><button data-file="open">Открыть базу</button></div></div>';return;}
  try {
    if(state.view==='components') await renderComponents(version);
    else if(state.view==='compare') await renderCompare(version);
    else if(state.editor) await renderEditor();
    else await renderRecipes(version);
    if(restoreSearch&&$('#query')){$('#query').focus();$('#query').setSelectionRange(state.query.length,state.query.length);}
  } catch(e){notify(e.message,true);}
}
async function renderRecipes(version) {
  const rows=await api('list_recipes',{query:state.query,color_code:state.color||null,manufactured_month:state.filterMonth||null,period:state.period,cost_mode:state.costMode,sort:state.recipeSort,descending:state.recipeDesc});
  if(version!==state.render)return;state.recipes=rows;
  main.innerHTML=`<div class="titlebar"><h1>Рецепты</h1><div class="actions"><button id="compare-selected" ${state.selected.size?'':'disabled'}>Сравнить${state.selected.size?' ('+state.selected.size+')':''}</button><button id="add-recipe" class="primary">Создать рецепт</button></div></div>
  <div class="toolbar"><input id="query" class="search" type="search" aria-label="Поиск рецептов" placeholder="Поиск" value="${esc(state.query)}"><input id="color-filter" style="width:125px" aria-label="Код цвета" placeholder="Код цвета" value="${esc(state.color)}"><label>Изготовлено <input id="month-filter" type="month" value="${esc(state.filterMonth)}"></label><label>Цены <input id="period" type="month" value="${state.period}"></label><select id="cost-mode" aria-label="Режим стоимости"><option value="selected">За партию</option><option value="per_kg">За 1 кг</option><option value="snapshot">При сохранении</option><option value="current">Текущая</option></select></div>
  <div class="table-wrap"><table><thead><tr><th class="check"></th>${sortHead('Код цвета','color_code','recipe')}${sortHead('Название','name','recipe')}${sortHead('Изготовлено','manufactured_on','recipe')}${sortHead('Масса, г','mass_grams','recipe',true)}${sortHead('Стоимость, ₽','cost','recipe',true)}${sortHead('Добавлено','created_at','recipe')}${sortHead('Изменено','updated_at','recipe')}</tr></thead><tbody>${rows.map(r=>`<tr class="${state.selected.has(r.id)?'selected':''}"><td class="check"><input type="checkbox" data-select="${r.id}" aria-label="Выбрать ${esc(title(r))}" ${state.selected.has(r.id)?'checked':''}></td><td class="code">${esc(r.color_code)||'—'}</td><td><button class="row-open" data-recipe="${r.id}">${esc(title(r))}</button>${r.vehicle?`<div class="sub">${esc(r.vehicle)}</div>`:''}</td><td class="nowrap">${displayDate(r.manufactured_on)}</td><td class="num">${fmt(r.mass_grams)}</td><td class="num" title="${esc(r.missing.join(', '))}">${fmt(r.cost)}</td><td class="sub nowrap">${displayTime(r.created_at)}</td><td class="sub nowrap">${displayTime(r.updated_at)}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">Рецептов пока нет</td></tr>'}</tbody></table></div>`;
  $('#cost-mode').value=state.costMode;$('#cost-mode').onchange=e=>{state.costMode=e.target.value;render();};
  $('#color-filter').onchange=e=>{state.color=e.target.value.trim();render();};$('#month-filter').onchange=e=>{state.filterMonth=e.target.value;render();};
  $('#add-recipe').onclick=()=>openRecipe();
  $$('[data-recipe]').forEach(b=>b.onclick=()=>openRecipe(Number(b.dataset.recipe)));
  $$('[data-select]').forEach(b=>b.onchange=()=>{const id=Number(b.dataset.select);b.checked?state.selected.add(id):state.selected.delete(id);b.closest('tr').classList.toggle('selected',b.checked);$('#compare-selected').disabled=!state.selected.size;$('#compare-selected').textContent='Сравнить'+(state.selected.size?' ('+state.selected.size+')':'');});
  $('#compare-selected').onclick=()=>{state.compareIds=[...state.selected];state.view='compare';render();};bindSort('recipe');bindToolbar();status(`Рецептов: ${rows.length}`);
}

async function renderComponents(version) {
  const rows=await api('list_components',{query:state.query,period:state.period,sort:state.componentSort,descending:state.componentDesc});
  if(version!==state.render)return;state.components=rows;
  main.innerHTML=`<div class="titlebar"><h1>Компоненты</h1><div class="actions"><button id="import">Импорт Excel</button><button id="export">Экспорт Excel</button><button id="add-component" class="primary">Добавить компонент</button></div></div><div class="toolbar"><input id="query" class="search" type="search" aria-label="Поиск компонентов" placeholder="Код, название или алиас" value="${esc(state.query)}"><label>Цены за месяц <input id="period" type="month" value="${state.period}"></label></div>
  <div class="table-wrap"><table><thead><tr>${sortHead('Код','code','component')}${sortHead('Название','name','component')}<th class="num">Упаковка, ₽</th><th class="num">Объём, л</th><th class="num">Масса литра, г</th>${sortHead('Цена, ₽/г','price_per_gram','component',true)}<th>Прайс</th>${sortHead('Изменено','updated_at','component')}</tr></thead><tbody>${rows.map(r=>`<tr><td><button class="row-open code" data-component="${r.id}">${esc(r.code)}</button></td><td>${esc(r.name)}${r.aliases.length?`<div class="sub">${esc(r.aliases.join(', '))}</div>`:''}</td><td class="num">${fmt(r.price?.package_price)}</td><td class="num">${fmt(r.price?.volume_liters)}</td><td class="num">${fmt(r.price?.grams_per_liter)}</td><td class="num">${fmt(r.price_per_gram)}</td><td class="nowrap ${r.price?.period!==state.period?'muted':''}">${r.price?.period||'Нет цены'}</td><td class="sub nowrap">${displayTime(r.updated_at)}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">Компонентов пока нет</td></tr>'}</tbody></table></div>`;
  $$('[data-component]').forEach(b=>b.onclick=()=>componentDialog(Number(b.dataset.component)));
  $('#add-component').onclick=()=>componentDialog();$('#import').onclick=()=>importDialog();
  $('#export').onclick=async()=>{const context=state.context,period=state.period;const path=await window.pywebview.api.choose_file('export');if(!path)return;try{await api('export_components',{path,period},context);notify('Компоненты экспортированы');}catch(e){notify(e.message,true);}};
  bindSort('component');bindToolbar();status(`Компонентов: ${rows.length}`);
}
function field(label,id,value='',type='text',className='') {
  return `<label class="field ${className}"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(value)}"></label>`;
}
async function componentDialog(id) {
  try {
    const context=state.context,c=id?await api('get_component',{id}):{code:'',name:'',aliases:[],prices:[]};
    let price=c.prices.find(p=>p.period===state.period)||c.prices.find(p=>p.period<state.period);
    showDialog(id?'Компонент':'Новый компонент',`<div class="form-grid" style="grid-template-columns:1fr 2fr">${field('Код','c-code',c.code)}${field('Название','c-name',c.name)}${field('Алиасы через точку с запятой','c-aliases',c.aliases.join('; '),'text','full')}</div><h3>Цена</h3><div class="form-grid" style="grid-template-columns:1fr 1fr">${field('Месяц','c-period',state.period,'month')}${field('Цена упаковки, ₽','c-price',price?.package_price??'')}${field('Объём упаковки, л','c-volume',price?.volume_liters??'')}${field('Масса литра, г','c-density',price?.grams_per_liter??'')}</div><div id="price-preview" class="sub" style="margin-top:12px"></div>${id?`<details><summary>История цен (${c.prices.length})</summary><div class="history-table"><table><thead><tr><th>Месяц</th><th class="num">Упаковка, ₽</th><th class="num">Цена, ₽/г</th><th></th></tr></thead><tbody>${c.prices.map(p=>`<tr><td><button class="row-open" data-price="${p.period}">${p.period}</button></td><td class="num">${fmt(p.package_price)}</td><td class="num">${fmt(p.price_per_gram)}</td><td><button class="quiet icon" data-delete-price="${p.period}" aria-label="Удалить цену ${p.period}">×</button></td></tr>`).join('')}</tbody></table></div></details>`:''}`,`${id?'<button id="delete-component" class="danger" style="margin-right:auto">Удалить</button>':''}<button data-close>Отмена</button><button id="save-component" class="primary">Сохранить</button>`);
    const update=()=>{const p=Number($('#c-price').value.replace(',','.')),v=Number($('#c-volume').value.replace(',','.')),d=Number($('#c-density').value.replace(',','.'));$('#price-preview').textContent=($('#c-price').value!==''&&p>=0&&v>0&&d>0)?`${fmt(v*d)} г · ${fmt(p/(v*d))} ₽/г`:'';};update();
    $$('input',$('#dialog')).forEach(e=>e.oninput=()=>{beginEdit();update();});
    $$('[data-price]').forEach(b=>b.onclick=()=>{price=c.prices.find(p=>p.period===b.dataset.price);$('#c-period').value=price.period;$('#c-price').value=price.package_price;$('#c-volume').value=price.volume_liters;$('#c-density').value=price.grams_per_liter;update();});
    $('#save-component').onclick=e=>runForm(e.target,async()=>{const values=[$('#c-price').value,$('#c-volume').value,$('#c-density').value];const data={id:id??null,revision:c.revision??null,code:$('#c-code').value,name:$('#c-name').value,aliases:$('#c-aliases').value.split(';').map(x=>x.trim()).filter(Boolean)};if(values.some(x=>x!==''))data.price={period:$('#c-period').value,package_price:values[0],volume_liters:values[1],grams_per_liter:values[2]};await api('save_component',data,context);window.dirty=false;$('#dialog').close();await render();notify('Компонент сохранён');});
    $('#delete-component')?.addEventListener('click',e=>runForm(e.target,async()=>{if(!confirm(`Удалить компонент ${c.code}?`))return;await api('delete_component',{id,revision:c.revision},context);window.dirty=false;$('#dialog').close();await render();notify('Компонент удалён');}));
    $$('[data-delete-price]').forEach(b=>b.onclick=()=>runForm(b,async()=>{if(!confirm(`Удалить цену за ${b.dataset.deletePrice}?`))return;await api('delete_price',{component_id:id,period:b.dataset.deletePrice,revision:c.revision},context);window.dirty=false;await componentDialog(id);}));
  } catch(e){notify(e.message,true);}
}

async function openRecipe(id,duplicate=false) {
  if(!allowLeave())return;
  try {
    const r=id?await api('get_recipe',{id,period:state.period}):{name:'',color_code:'',brand:'',vehicle:'',work_order:'',comment:'',manufactured_on:state.today,lines:[{component_id:null,mass_expression:'',code:'',name:''}]};
    if(duplicate){delete r.id;delete r.revision;delete r.snapshot_total;r.manufactured_on=state.today;}
    state.editor={...r,context:state.context};state.view='recipes';state.historyMode='per_kg';window.dirty=duplicate;await render();
  }catch(e){notify(e.message,true);}
}
function readEditor() {
  const r=state.editor;for(const key of ['name','color_code','brand','vehicle','work_order','comment','manufactured_on']){const input=$('#r-'+key);if(input)r[key]=input.value;}
  $$('.recipe-line').forEach((tr,i)=>{r.lines[i].mass_expression=$('.mass-expression',tr).value;});return r;
}
function lineMarkup(line,i) {
  return `<tr class="recipe-line" data-index="${i}"><td><div class="line-search"><input class="component-search" aria-label="Компонент ${i+1}" autocomplete="off" placeholder="Код или название" value="${esc(line.code?line.code+' · '+line.name:'')}"><div class="suggestions" hidden></div></div></td><td><input class="mass-expression" aria-label="Масса ${i+1}" placeholder="0.000" value="${esc(line.mass_expression)}"></td><td class="num line-mass">${line.mass_grams?fmt(line.mass_grams):'—'}</td><td class="num line-cost">—</td><td style="width:42px"><button class="quiet icon remove-line" aria-label="Удалить строку ${i+1}">×</button></td></tr>`;
}
async function renderEditor() {
  const r=state.editor;
  main.innerHTML=`<div class="editor"><div class="titlebar"><button id="back" class="quiet">← Рецепты</button><h1>${r.id?esc(title(r)):'Новый рецепт'}</h1><div class="actions">${r.id?'<button id="duplicate">Копировать</button>':''}<button id="save-recipe" class="primary">Сохранить</button></div></div>
  <div class="form-grid">${field('Название','r-name',r.name)}${field('Код цвета','r-color_code',r.color_code)}${field('Марка краски','r-brand',r.brand)}${field('Автомобиль','r-vehicle',r.vehicle)}${field('Заказ-наряд','r-work_order',r.work_order)}${field('Дата изготовления','r-manufactured_on',r.manufactured_on,'date')}<label class="field full"><span>Комментарий</span><textarea id="r-comment">${esc(r.comment)}</textarea></label></div>
  <div class="split"><h3>Состав</h3><label class="sub">Цены <input id="calc-period" type="month" value="${state.period}"></label></div>
  <div class="table-wrap"><table><thead><tr><th>Компонент</th><th>Масса или выражение</th><th class="num">Масса, г</th><th class="num">Стоимость, ₽</th><th style="width:42px"></th></tr></thead><tbody id="lines">${r.lines.map(lineMarkup).join('')}</tbody></table></div>
  <div class="editor-buttons"><button id="add-line">Добавить строку</button>${r.id?'<button id="delete-recipe" class="quiet danger">Удалить рецепт</button>':''}</div><div id="editor-error" class="error-text" role="alert"></div>
  <div class="totals"><div class="total"><span>Масса, г</span><strong id="total-mass">—</strong></div><div class="total"><span>Стоимость, ₽</span><strong id="total-cost">—</strong></div><div class="total"><span>За 1 кг, ₽</span><strong id="total-kg">—</strong></div>${r.id?`<div class="total"><span>При сохранении, ₽</span><strong>${fmt(r.snapshot_total)}</strong></div><div class="total"><span>Текущая, ₽</span><strong>${fmt(r.current?.total)}</strong></div>`:''}</div>
  ${r.id?`<details><summary>Исходный расчёт</summary><table><thead><tr><th>Компонент</th><th>Выражение</th><th class="num">Цена, ₽/г</th><th>Месяц прайса</th><th class="num">Стоимость, ₽</th></tr></thead><tbody>${r.lines.map(l=>`<tr><td>${esc(l.code)}</td><td>${esc(l.mass_expression)}</td><td class="num">${fmt(l.snapshot_price)}</td><td>${esc(l.snapshot_period)}</td><td class="num">${fmt(l.snapshot_price*l.mass_grams)}</td></tr>`).join('')}</tbody></table></details><div id="history"></div>`:''}</div>`;
  $('#back').onclick=()=>{if(allowLeave()){state.editor=null;render();}};$('#duplicate')?.addEventListener('click',()=>openRecipe(r.id,true));
  $$('.form-grid input,.form-grid textarea',main).forEach(e=>e.oninput=()=>{beginEdit();readEditor();});
  $('#calc-period').onchange=e=>{if(e.target.value){state.period=e.target.value;recalculate();}};
  $('#add-line').onclick=()=>{readEditor();r.lines.push({component_id:null,mass_expression:'',code:'',name:''});$('#lines').insertAdjacentHTML('beforeend',lineMarkup(r.lines.at(-1),r.lines.length-1));bindLines();beginEdit();$('.recipe-line:last-child .component-search').focus();};
  $('#save-recipe').onclick=e=>saveRecipe(e.target);
  $('#delete-recipe')?.addEventListener('click',async()=>{if(!confirm(`Удалить ${title(r)}?`))return;try{await api('delete_recipe',{id:r.id,revision:r.revision},r.context);window.dirty=false;state.editor=null;state.selected.delete(r.id);await render();notify('Рецепт удалён');}catch(e){$('#editor-error').textContent=e.message;}});
  bindLines();await recalculate(false);if(r.id)await historyPanel([r.id],$('#history'),false);status(r.id?`Добавлено ${displayTime(r.created_at)} · ${r.source==='mcp'?'MCP':'Интерфейс'}`:'Новый рецепт');
}
let calcTimer,calcVersion=0;
function bindLines() {
  $$('.recipe-line').forEach((tr,i)=>{
    const input=$('.component-search',tr),suggest=$('.suggestions',tr);
    input.oninput=async()=>{
      const query=input.value;state.editor.lines[i].component_id=null;state.editor.lines[i].code='';beginEdit();
      try {const rows=await api('list_components',{query,period:state.period},state.editor.context);if(input.value!==query)return;suggest.hidden=false;suggest.innerHTML=rows.slice(0,30).map(c=>`<button type="button" data-candidate="${c.id}">${esc(c.code)} · ${esc(c.name)}</button>`).join('')||'<div style="padding:10px">Компонент не найден</div>';
      $$('button',suggest).forEach(b=>b.onmousedown=e=>{e.preventDefault();const c=rows.find(c=>c.id===Number(b.dataset.candidate));Object.assign(state.editor.lines[i],{component_id:c.id,code:c.code,name:c.name});input.value=c.code+' · '+c.name;suggest.hidden=true;beginEdit();recalculate();});}catch(e){$('#editor-error').textContent=e.message;}
    };
    input.onfocus=()=>{if(!input.value)input.oninput();};input.onblur=()=>setTimeout(()=>{if(!suggest.contains(document.activeElement))suggest.hidden=true;},150);
    input.onkeydown=e=>{if(e.key==='ArrowDown'&&!suggest.hidden){e.preventDefault();$('button',suggest)?.focus();}if(e.key==='Escape')suggest.hidden=true;};
    suggest.onkeydown=e=>{const buttons=$$('button',suggest),index=buttons.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();buttons[(index+1)%buttons.length]?.focus();}if(e.key==='ArrowUp'){e.preventDefault();buttons[(index-1+buttons.length)%buttons.length]?.focus();}if(e.key==='Enter'){e.preventDefault();document.activeElement.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));}};
    $('.mass-expression',tr).oninput=()=>{beginEdit();readEditor();clearTimeout(calcTimer);calcTimer=setTimeout(()=>recalculate(),200);};
    $('.remove-line',tr).onclick=()=>{readEditor();state.editor.lines.splice(i,1);$('#lines').innerHTML=state.editor.lines.map(lineMarkup).join('');bindLines();beginEdit();recalculate(false);};
  });
}
async function recalculate(showError=true) {
  if(!state.editor||!$('#total-cost'))return;
  const generation=++calcVersion,r=readEditor();
  $('#editor-error').textContent='';
  try {
    const calc=await api('calculate',{lines:r.lines.map(l=>({component_id:l.component_id,mass_expression:l.mass_expression})),period:state.period},r.context);
    if(generation!==calcVersion||!$('#total-cost'))return;
    $('#total-mass').textContent=fmt(calc.mass_grams);$('#total-cost').textContent=fmt(calc.total);$('#total-kg').textContent=fmt(calc.per_kg);
    $$('.recipe-line').forEach((tr,i)=>{if(!calc.lines[i])return;$('.line-mass',tr).textContent=fmt(calc.lines[i].mass_grams);$('.line-cost',tr).textContent=fmt(calc.lines[i].cost);$('.line-cost',tr).title=calc.lines[i].price_period?'Прайс '+calc.lines[i].price_period:'Нет цены';});
    if(calc.missing.length)$('#editor-error').textContent='Нет цены за выбранный месяц: '+calc.missing.join(', ');
  }catch(e){if(generation!==calcVersion||!$('#total-cost'))return;$('#total-mass').textContent='—';$('#total-cost').textContent='—';$('#total-kg').textContent='—';$$('.line-cost,.line-mass').forEach(x=>x.textContent='—');if(showError)$('#editor-error').textContent=e.message;}
}
async function saveRecipe(button) {
  button.disabled=true;try {
    const r=readEditor(),data={};for(const k of ['name','color_code','brand','vehicle','work_order','comment','manufactured_on'])data[k]=r[k];
    data.lines=r.lines.map(l=>({component_id:l.component_id,mass_expression:l.mass_expression}));if(r.id){data.id=r.id;data.revision=r.revision;}
    const saved=await api('save_recipe',data,r.context);window.dirty=false;state.editor={...saved,context:r.context};await render();notify('Рецепт сохранён');
  }catch(e){$('#editor-error').textContent=e.message;}finally{button.disabled=false;}
}

async function renderCompare(version) {
  const ids=state.compareIds.length?state.compareIds:[...state.selected];
  if(!ids.length){main.innerHTML='<div class="titlebar"><h1>Сравнение</h1></div><div class="empty"><p>Выберите рецепты одного цвета в списке</p><button id="to-recipes">Открыть рецепты</button></div>';$('#to-recipes').onclick=()=>{state.view='recipes';render();};return;}
  const rows=await api('compare_recipes',{ids,period:state.period});if(version!==state.render)return;
  main.innerHTML=`<div class="titlebar"><h1>Сравнение${rows[0].color_code?' · '+esc(rows[0].color_code):''}</h1><div class="actions"><button id="choose-recipes">Выбрать рецепты</button></div></div><div class="toolbar"><label>Цены <input id="period" type="month" value="${state.period}"></label><span class="sub">Масса сравнения: 1000.000 г</span></div><div class="comparison">${rows.map(r=>`<article class="variant"><h2>${esc(title(r))}</h2><div class="sub">${displayDate(r.manufactured_on)} · исходная масса ${fmt(r.snapshot_mass)} г</div><div class="value">${fmt(r.calculation.total)} <span class="sub">₽/кг</span></div><table><thead><tr><th>Компонент</th><th class="num">Доля, %</th><th class="num">На 1 кг, г</th></tr></thead><tbody>${r.calculation.lines.map(l=>`<tr><td title="${esc(l.name)}">${esc(l.code)}</td><td class="num">${fmt(l.share*100)}</td><td class="num">${fmt(l.mass_grams)}</td></tr>`).join('')}</tbody></table><div class="sub" style="margin-top:14px">Исходная стоимость: ${fmt(r.snapshot_total)} ₽</div>${r.calculation.missing.length?`<div class="error-text">Нет цены: ${esc(r.calculation.missing.join(', '))}</div>`:''}</article>`).join('')}</div><div id="history"></div>`;
  $('#choose-recipes').onclick=()=>{state.view='recipes';render();};bindToolbar();await historyPanel(ids,$('#history'),true);status(`Вариантов: ${rows.length}`);
}
async function historyPanel(ids,container,comparison) {
  if(!container)return;
  const end=state.period,start=(Number(end.slice(0,4))-1)+end.slice(4);
  container.innerHTML=`<div class="chart-controls"><h3 style="margin:0 auto 0 0">Стоимость по месяцам</h3><label>С <input id="history-start" type="month" value="${start}"></label><label>По <input id="history-end" type="month" value="${end}"></label>${!comparison?'<select id="history-mode" aria-label="Масса для графика"><option value="per_kg">За 1 кг</option><option value="batch">За партию</option></select>':''}</div><div id="chart"></div>`;
  if($('#history-mode'))$('#history-mode').value=state.historyMode;
  const update=async()=>{try {const data=await api('cost_history',{ids,start:$('#history-start').value,end:$('#history-end').value,mode:comparison?'per_kg':$('#history-mode').value});if(!$('#chart'))return;$('#chart').innerHTML=drawChart(data);if($('#history-mode'))state.historyMode=$('#history-mode').value;}catch(e){if($('#chart'))$('#chart').innerHTML=`<p class="error-text">${esc(e.message)}</p>`;}};
  $$('input,select',container).forEach(e=>e.onchange=update);await update();
}
function drawChart(data) {
  const palette=['#0078d4','#c76413','#107c10','#8764b8','#c239b3','#038387','#a4262c','#5c2d91','#486860','#8c6b22','#4f6bed','#737373'];
  const values=data.series.flatMap(s=>s.values.map(v=>v.total).filter(v=>v!==null));
  const maximum=Math.max(...values,1)*1.1,width=960,height=250,left=78,right=18,top=16,bottom=37;
  const x=i=>left+i*(width-left-right)/Math.max(data.periods.length-1,1), y=n=>height-bottom-n/maximum*(height-top-bottom);
  let svg='';for(let i=0;i<=4;i++){const v=maximum*i/4,yy=y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#e5e5e5"/><text x="${left-10}" y="${yy+4}" text-anchor="end" fill="#666" font-size="11">${fmt(v)}</text>`;}
  const step=Math.max(1,Math.ceil(data.periods.length/12));data.periods.forEach((p,i)=>{if(i%step===0||i===data.periods.length-1)svg+=`<text x="${x(i)}" y="${height-10}" text-anchor="middle" fill="#666" font-size="11">${p}</text>`;});
  data.series.forEach((s,k)=>{let segment='';s.values.forEach((v,i)=>{if(v.total===null){if(segment)svg+=`<path d="${segment}" fill="none" stroke="${palette[k]}" stroke-width="2"/>`;segment='';return;}segment+=(segment?' L':'M')+x(i)+' '+y(v.total);svg+=`<circle cx="${x(i)}" cy="${y(v.total)}" r="4" fill="${palette[k]}"><title>${esc(title(s))} · ${data.periods[i]} · ${fmt(v.total)} ${data.mode==='per_kg'?'₽/кг':'₽'}</title></circle>`;});if(segment)svg+=`<path d="${segment}" fill="none" stroke="${palette[k]}" stroke-width="2" pointer-events="none"/>`;});
  const gaps=data.series.some(s=>s.values.some(v=>v.total===null));
  return `<div class="chart"><div class="split"><div class="legend">${data.series.map((s,k)=>`<span><i style="background:${palette[k]}"></i>${esc(title(s))} · ${displayDate(s.manufactured_on)}</span>`).join('')}</div><span class="sub">${data.mode==='per_kg'?'₽/кг':'₽ за партию'}</span></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="График стоимости по месяцам">${svg}</svg>${gaps?'<div class="sub">Разрывы: нет цен для полного расчёта</div>':''}</div><details><summary>Значения по месяцам</summary><div class="chart-table"><table><thead><tr><th>Месяц</th>${data.series.map(s=>`<th class="num">${esc(title(s))}</th>`).join('')}</tr></thead><tbody>${data.periods.map((p,i)=>`<tr><td>${p}</td>${data.series.map(s=>`<td class="num" title="${esc(s.values[i].missing.join(', '))}">${s.values[i].total===null?'Нет цены: '+esc(s.values[i].missing.join(', ')):fmt(s.values[i].total)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
}

async function importDialog() {
  const context=state.context,path=await window.pywebview.api.choose_file('import');if(!path)return;
  let preview=null;
  showDialog('Импорт компонентов',`<div class="import-path">${esc(path)}</div><div class="import-toolbar"><label>Месяц <input id="import-period" type="month" aria-label="Месяц импорта"></label><button id="check-import">Проверить</button><span id="import-summary" class="sub"></span></div><div id="import-rows"></div>`,`<span class="sub" id="selected-count"></span><button data-close>Отмена</button><button id="apply-import" class="primary" disabled>Импортировать выбранные</button>`,true);
  const selected=()=>$$('[data-import-row]:checked').map(b=>b.dataset.importRow);
  const update=()=>{const count=selected().length;$('#selected-count').textContent=preview?`Выбрано ${count} из ${preview.rows.length}`:'';$('#apply-import').disabled=!count;};
  const check=async()=>{const b=$('#check-import');b.disabled=true;$('#dialog-error').textContent='';$('#apply-import').disabled=true;
    try {preview=await api('preview_import',{path,period:$('#import-period').value||null},context);$('#import-period').value=preview.period.match(/^\d{4}-\d{2}$/)?preview.period:'';
    $('#import-summary').textContent=`Строк: ${preview.rows.length} · С ошибками: ${preview.errors}`;
    $('#import-rows').innerHTML=`<div class="table-wrap import-table"><table><thead><tr><th></th><th>Лист · строка</th><th>Код</th><th>Название</th><th class="num">Цена, ₽/г</th><th>Проверка</th></tr></thead><tbody>${preview.rows.map(r=>`<tr><td><input type="checkbox" data-import-row="${esc(r.key)}" aria-label="Импортировать строку ${r.row}" ${r.selected?'checked':''} ${r.errors.length?'disabled':''}></td><td class="nowrap">${esc(r.sheet)} · ${r.row}</td><td>${esc(r.code)}</td><td>${esc(r.name)}</td><td class="num">${fmt(r.price?.price_per_gram)}</td><td class="problem ${r.errors.length?'error-text':'warning'}">${esc([...r.errors,...r.warnings].join('; '))||'Готово'}</td></tr>`).join('')}</tbody></table></div>`;
    $$('[data-import-row]').forEach(b=>b.onchange=update);update();
    }catch(e){preview=null;$('#import-rows').innerHTML='';$('#dialog-error').textContent=e.message;}finally{b.disabled=false;}
  };
  $('#check-import').onclick=check;$('#import-period').onchange=()=>{$('#apply-import').disabled=true;preview=null;$('#selected-count').textContent='Повторите проверку';};
  $('#apply-import').onclick=e=>runForm(e.target,async()=>{if(!preview)return;const result=await api('apply_import',{token:preview.token,selected_rows:selected()},context);$('#dialog').close();await render();notify(`Импорт завершён: добавлено ${result.created}, обновлено ${result.updated}, без прайса ${result.without_price}`);});
  await check();
}

let polling=false;
async function poll() {
  if(polling||!window.appReady)return;polling=true;
  try {
    const result=await api('events',{after:state.sequence});
    const switched=result.context!==state.context;
    if(switched){setDatabase(result);state.selected.clear();state.compareIds=[];if(!window.dirty&&!$('#dialog').open){state.editor=null;await render();}else notify('Открыта другая база. Несохранённая форма относится к прежней базе',true);}
    state.sequence=result.sequence;
    const changes=result.items.filter(e=>e.source==='mcp'&&e.entity!=='database');
    if(changes.length){const last=changes.at(-1);notify(`${last.action}: ${last.label||last.count} · MCP`,false,last.action.startsWith('Удалён')||last.action.startsWith('Удалена')?null:async()=>{if(!allowLeave())return;if($('#dialog').open)$('#dialog').close();if(last.entity==='recipe')await openRecipe(last.ids[0]);else{state.view='components';state.editor=null;await render();if(last.ids.length===1)await componentDialog(last.ids[0]);}});
      if(!window.dirty&&!$('#dialog').open&&!state.editor)await render();
    }
  }catch(e){status(e.message);}finally{polling=false;}
}
window.addEventListener('pywebviewready',async()=>{try{setDatabase(await api('status'));await render();window.appReady=true;setInterval(poll,1200);if(window.startupError)notify(window.startupError,true);}catch(e){notify(e.message,true);}});
