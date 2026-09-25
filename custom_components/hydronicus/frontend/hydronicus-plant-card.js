var C="\xB0C";var bn=5;var vn=35;function _e(n){return n?.temperature==="\xB0F"?"\xB0F":C}function K(n,e){return e==="\xB0F"?n*9/5+32:n}function _n(n,e){return e==="\xB0F"?n*9/5:n}function xe(n){return n==="\xB0F"?1:.5}function it(n,e,t){const r=xe(t);const o=K(n,t);const a=o/r;const i=(e>0?Math.floor(a+1e-9)+1:Math.ceil(a-1e-9)-1)*r;const u=K(bn,t);const l=K(vn,t);return Number(Math.min(l,Math.max(u,i)).toFixed(1))}function xn(n){switch(n?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return n?.language}}var at=new Map;function g(n,e,t=1){const r=xn(e);const o=e?.number_format!=="none";const a=`${JSON.stringify(r)}|${t}|${o}`;let i=at.get(a);if(!i){try{i=new Intl.NumberFormat(r,{minimumFractionDigits:t,maximumFractionDigits:t,useGrouping:o})}catch{i=new Intl.NumberFormat(void 0,{minimumFractionDigits:t,maximumFractionDigits:t})}at.set(a,i)}return i.format(n)}function G(n,e,t){return g(K(n,e),t)}function st(n,e,t){return g(_n(n,e),t)}var wn=2;var $n=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function lt(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const e=n;if(e.schema_version!==wn){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(e.schema_version)}.`)}if(!e.plant||!Array.isArray(e.zones)||!Array.isArray(e.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return e}function we(n){return[...n.alerts].sort((e,t)=>e.priority-t.priority||e.code.localeCompare(t.code)||e.scope.localeCompare(t.scope))}function ct(n){const e=n.plant.health.toLowerCase();const t=n.alerts.some(dt);if(n.safe_shutdown.active||t||["blocked","critical","degraded","error","failed","unavailable","unhealthy"].includes(e)){return"attention"}const r=`${n.plant.active_mode} ${n.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function dt(n){return n.severity==="critical"||n.severity==="error"}function X(n,e){return we(n).filter(t=>t.scope===e)}function ut(n,e=[]){if(n.blocked||e.some(dt))return"attention";if(n.cooling.demand)return"cooling";if(n.demand)return"heating";return"idle"}function $e(n){return $n.has(n.toLowerCase())}function Y(n){if(!n)return"none";return n.cooling.demand?"cooling":n.demand?"heating":"none"}function ht(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:n.thermostat.control_entity_id,temperature:e}}}function pt(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:n.thermostat.control_entity_id,preset_mode:e}}}function mt(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;if(!ke(n).includes(e))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:n.thermostat.control_entity_id,hvac_mode:e}}}function ft(n,e){if(!n.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:n.controls.requested_mode,option:e}}}function gt(n){if(!n.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:n.controls.safe_shutdown}}}function yt(n){const e=String(n.action??"operation").replaceAll("_"," ");const t=String(n.actuator_name??"actuator");const r=String(n.result??"");if(r==="proposed")return`Would ${e} ${t}`;if(r==="executed")return`Executed ${t} ${e}`;if(r==="suppressed")return`Suppressed ${t} ${e}`;return`${r||"Operation"}: ${t} ${e}`}function kn(n){return n.replaceAll("_"," ")}function N(n,e,t){const[r,o]=e.split(".");return n?.(`component.hydronicus.entity.${r}.${o}.state.${t}`)||f(t)}function f(n){const e=kn(n);return e.charAt(0).toUpperCase()+e.slice(1)}var Sn={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function J(n,e){return n?.(`component.climate.entity_component._.state.${e}`)||Sn[e]||f(e)}function ke(n){if(n.thermostat.kind!=="hydronicus")return[];return[...new Set(n.thermostat.hvac_modes??[])]}function Se(n){return n.areas.length>=2?n.areas:[]}function Q(n){return 5+Math.ceil(Se(n).length/2)}function bt(n,e){if(n.thermostat.hvac_mode==="off")return{label:J(e,"off"),kind:"off"};if(n.blocked)return{label:"Blocked",kind:"blocked"};return{label:f(n.phase),kind:"phase"}}var Cn={degraded:"Degraded",unavailable:"Entity unavailable"};function vt(n){return Cn[n]??null}function Ce(n){if(n.dry_run||n.mode==="dry_run")return"Dry run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"Live";return f(n.mode)}function _t(n){if(n.dry_run||n.mode==="dry_run")return"dry-run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"live";return n.mode.replaceAll("_","-")}function xt(n){const{active_name:e,recommended_name:t}=n.plant.source;if(!n.sources.length&&!e&&!t)return null;const r=[e??"None active"];if(t&&t!==e)r.push(`recommended ${t}`);return r.join(" \xB7 ")}var An={zone:"Zone",circuit:"Loop"};var En={plant_initializing:"Starting",plant_unavailable:"Plant unavailable",binding_unavailable:"Entity unavailable",zone_sensor_blocked:"Sensor blocked",zone_mode_blocked:"Zone blocked",cooling_blocked:"Cooling blocked",actuator_mismatch:"Equipment mismatch",actuator_blocked:"Equipment blocked",mode_changeover:"Mode changeover",sensor_unavailable:"Sensor missing",optional_sensor_unavailable:"Optional sensor missing",zone_area_missing:"Area missing",zone_without_temperature_source:"No temperature sensor",zone_area_self_feed:"Area sensor ignored"};function Ae(n){return En[n]??f(n)}function wt(n){const e=Ae(n.code);return n.scope!=="plant"&&n.name?`${n.name} \xB7 ${e}`:e}function Ee(n){return An[n]??f(n)}function $t(n){return[...new Set(n.thermostat.preset_modes)].filter(e=>e!=="none")}function kt(n,e,t=C){if(n.thermostat.target_temperature===null)return null;return it(n.thermostat.target_temperature,e,t)}var Pn="hydronicus/subscribe_plant";var zn=1e3;var Tn=6e4;var Rn={setTimeout:(n,e)=>globalThis.setTimeout(n,e),clearTimeout:n=>globalThis.clearTimeout(n)};var St={plant_not_found:"not_found",unauthorized:"unauthorized"};function Ct(n){return n!==void 0&&Object.hasOwn(St,n)?St[n]:void 0}function Hn(n){return typeof n==="object"&&n!==null&&"code"in n?String(n.code):void 0}function Z(n,e){if(n instanceof Error)return n.message;if(typeof n==="object"&&n!==null&&"message"in n&&n.message){return String(n.message)}return e}function Pe(n){if(!n)return;try{void Promise.resolve(n()).catch(()=>void 0)}catch{}}var ee=class{constructor(e,t=Rn){this.host=e;this.scheduler=t}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(e,t){if(e===this.connection&&t===this.plantId)return;this.disconnect();if(!e||!t)return;this.connection=e;this.plantId=t;e.addEventListener?.("disconnected",this.handleDisconnected);e.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;Pe(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const e=this.connection;const t=this.plantId;if(!e||!t)return;this.cancelRetry();const r=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}e.subscribeMessage(o=>this.handleEvent(r,o),{type:Pn,plant_id:t},{resubscribe:false}).then(o=>{if(r!==this.generation){Pe(o);return}this.unsubscribe=o}).catch(o=>{if(r!==this.generation)return;this.handleError(o)})}handleEvent(e,t){if(e!==this.generation)return;if(t.snapshot!==void 0&&t.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(t.snapshot);return}if(t.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const r=Ct(t.status);if(r)this.stop({kind:r})}handleError(e){const t=Ct(Hn(e));if(t){this.stop({kind:t});return}const r=Math.min(zn*2**this.attempt,Tn);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:r,message:Z(e,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},r)}stop(e){this.cancelRetry();this.generation+=1;Pe(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(e)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(e){this.current=e;this.host.onStatus(e)}};var R={status:{kind:"idle"},snapshot:null,snapshotError:null};var Ln=new Set(["idle","unavailable","not_found","unauthorized"]);var ze=class{listeners=new Set;current=R;stream;constructor(e){this.stream=new ee({onStatus:t=>this.statusChanged(t),onSnapshot:t=>this.snapshotReceived(t)},e)}get state(){return this.current}open(e,t){this.stream.connect(e,t)}close(){this.stream.disconnect()}statusChanged(e){const t=Ln.has(e.kind)?null:this.current.snapshot;this.publish({...this.current,status:e,snapshot:t})}snapshotReceived(e){try{this.publish({...this.current,snapshot:lt(e),snapshotError:null})}catch(t){this.publish({...this.current,snapshot:null,snapshotError:Z(t,"Unsupported Hydronicus snapshot.")})}}publish(e){this.current=e;for(const t of[...this.listeners])t(e)}};var Te=class{constructor(e){this.scheduler=e}scheduler;feeds=new WeakMap;subscribe(e,t,r){let o=this.feeds.get(e);if(!o){o=new Map;this.feeds.set(e,o)}let a=o.get(t);const i=!a;if(!a){a=new ze(this.scheduler);o.set(t,a)}a.listeners.add(r);if(i)a.open(e,t);else r(a.state);const u=o;const l=a;let d=false;return()=>{if(d)return;d=true;l.listeners.delete(r);if(l.listeners.size)return;queueMicrotask(()=>{if(l.listeners.size||u.get(t)!==l)return;u.delete(t);l.close()})}}snapshot(e,t,r=2e3){return new Promise(o=>{let a=false;const i=d=>{if(a)return;a=true;clearTimeout(u);queueMicrotask(()=>l());o(d)};const u=setTimeout(()=>i(null),r);const l=this.subscribe(e,t,d=>{if(d.snapshot)i(d.snapshot);else if(["not_found","unauthorized"].includes(d.status.kind)||d.snapshotError)i(null)})})}};var H=new Te;var te="hydronicus-plant-card";var At=`custom:${te}`;var ne="hydronicus-zone-card";var Et=`custom:${ne}`;var re="hydronicus-zone-card-editor";var Mn="hydronicus/list_plants";var On=["comfortable","compact"];var Pt=[{value:"header",label:"Header and execution boundary"},{value:"alerts",label:"Alerts"},{value:"zones",label:"Zones"},{value:"paths",label:"Hydraulic flow"},{value:"equipment",label:"Equipment"},{value:"explanations",label:"Controller explanations"},{value:"operations",label:"Operation outcomes"}];var Re=Pt.map(n=>n.value);function zt(n,e,t){if(!n||typeof n!=="object"){throw new Error(`${e} requires a configuration.`)}const r=n;if(r.type!==t){throw new Error(`${e} type must be ${t}.`)}if(typeof r.plant!=="string"){throw new Error(`${e} requires one Plant UUID in \`plant\`.`)}return r}function Tt(n,e){const t=n??"comfortable";if(!On.includes(t)){throw new Error(`${e} density must be comfortable or compact.`)}return t}function qn(n){if(n===void 0||n===null)return void 0;if(!Array.isArray(n)){throw new Error("Hydronicus Plant card `sections` must be a list of section names.")}const e=new Set;for(const t of n){if(typeof t!=="string"||!Re.includes(t)){throw new Error(`Hydronicus Plant card section ${JSON.stringify(t)} is unknown. Use ${Re.join(", ")}.`)}if(e.has(t)){throw new Error(`Hydronicus Plant card section ${t} is listed twice.`)}e.add(t)}return n.length?n:void 0}function Me(n){const e="Hydronicus Plant card";const t=zt(n,e,At);const r=Tt(t.density,e);const o=qn(t.sections);return{type:At,plant:t.plant.trim(),density:r,...o?{sections:o}:{}}}function oe(n){return n?.sections??Re}function ae(n){const e="Hydronicus Zone card";const t=zt(n,e,Et);const r=t.zone??"";if(typeof r!=="string"){throw new Error(`${e} requires one Zone id in \`zone\`.`)}const o=Tt(t.density,e);return{type:Et,plant:t.plant.trim(),zone:r.trim(),density:o}}var He=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(e){if(this.connection===e&&this.pending)return this.pending;this.connection=e;this.pending=e.sendMessagePromise({type:Mn}).then(t=>{this.plants=Array.isArray(t.plants)?t.plants:[];return this.plants}).catch(()=>{if(this.connection===e)this.pending=null;return this.plants});return this.pending}async settled(e=2e3){if(!this.pending)return this.plants;let t;const r=new Promise(o=>{t=setTimeout(()=>o(this.plants),e)});try{return await Promise.race([this.pending,r])}finally{clearTimeout(t)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var _=new He;async function Rt(n){const e=n?.connection?await _.load(n.connection):_.known;return{plant:e[0]?.id??"",density:"comfortable"}}async function Ht(n){const e=n?.connection;const t=e?await _.load(e):_.known;const r=t[0]?.id??"";const o=e&&r?await H.snapshot(e,r):null;return{plant:r,zone:o?.zones[0]?.id??"",density:"comfortable"}}var Un={plant:"Hydronicus Plant",zone:"Zone",density:"Density",sections:"Sections"};var Nn={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",zone:"The Zone this card shows. Only Zones you can read are listed; one that is not listed shows its id.",density:"Compact uses less spacing for dense dashboards.",sections:"The parts of the Plant to show, in this order. Leave empty to show every section."};var Oe=n=>Un[n.name];var qe=n=>Nn[n.name];function Le(n){if(n.length===0)return{text:{}};return{select:{mode:"dropdown",options:n.map(e=>({value:e.id,label:e.name}))}}}var Lt={name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}};async function Mt(){const n=await _.settled();return{schema:[{name:"plant",required:true,selector:Le(n)},Lt,{name:"sections",selector:{select:{multiple:true,reorder:true,mode:"dropdown",options:Pt.map(e=>({...e}))}}}],computeLabel:Oe,computeHelper:qe,assertConfig:e=>{Me(e)}}}function Ot(n,e){return[{name:"plant",required:true,selector:Le(n)},{name:"zone",required:true,selector:Le(e)},Lt]}var ie=globalThis;var se=ie.ShadowRoot&&(void 0===ie.ShadyCSS||ie.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var Ue=Symbol();var qt=new WeakMap;var D=class{constructor(e,t,r){if(this._$cssResult$=true,r!==Ue)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(se&&void 0===e){const r=void 0!==t&&1===t.length;r&&(e=qt.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&qt.set(t,e))}return e}toString(){return this.cssText}};var Ut=n=>new D("string"==typeof n?n:n+"",void 0,Ue);var Ne=(n,...e)=>{const t=1===n.length?n[0]:e.reduce((r,o,a)=>r+(i=>{if(true===i._$cssResult$)return i.cssText;if("number"==typeof i)return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[a+1],n[0]);return new D(t,n,Ue)};var Nt=(n,e)=>{if(se)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const t of e){const r=document.createElement("style"),o=ie.litNonce;void 0!==o&&r.setAttribute("nonce",o),r.textContent=t.cssText,n.appendChild(r)}};var Ze=se?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(const r of e.cssRules)t+=r.cssText;return Ut(t)})(n):n;var{is:Zn,defineProperty:Dn,getOwnPropertyDescriptor:In,getOwnPropertyNames:Fn,getOwnPropertySymbols:Vn,getPrototypeOf:jn}=Object;var le=globalThis;var Zt=le.trustedTypes;var Bn=Zt?Zt.emptyScript:"";var Wn=le.reactiveElementPolyfillSupport;var I=(n,e)=>n;var De={toAttribute(n,e){switch(e){case Boolean:n=n?Bn:null;break;case Object:case Array:n=null==n?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=null!==n;break;case Number:t=null===n?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch(r){t=null}}return t}};var It=(n,e)=>!Zn(n,e);var Dt={attribute:true,type:String,converter:De,reflect:false,useDefault:false,hasChanged:It};Symbol.metadata??=Symbol("metadata"),le.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Dt){if(t.state&&(t.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=true),this.elementProperties.set(e,t),!t.noAccessor){const r=Symbol(),o=this.getPropertyDescriptor(e,r,t);void 0!==o&&Dn(this.prototype,e,o)}}static getPropertyDescriptor(e,t,r){const{get:o,set:a}=In(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:o,set(i){const u=o?.call(this);a?.call(this,i),this.requestUpdate(e,u,r)},configurable:true,enumerable:true}}static getPropertyOptions(e){return this.elementProperties.get(e)??Dt}static _$Ei(){if(this.hasOwnProperty(I("elementProperties")))return;const e=jn(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(I("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(I("properties"))){const t=this.properties,r=[...Fn(t),...Vn(t)];for(const o of r)this.createProperty(o,t[o])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[r,o]of t)this.elementProperties.set(r,o)}this._$Eh=new Map;for(const[t,r]of this.elementProperties){const o=this._$Eu(t,r);void 0!==o&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const r=new Set(e.flat(1/0).reverse());for(const o of r)t.unshift(Ze(o))}else void 0!==e&&t.push(Ze(e));return t}static _$Eu(e,t){const r=t.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Nt(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){const r=this.constructor.elementProperties.get(e),o=this.constructor._$Eu(e,r);if(void 0!==o&&true===r.reflect){const a=(void 0!==r.converter?.toAttribute?r.converter:De).toAttribute(t,r.type);this._$Em=e,null==a?this.removeAttribute(o):this.setAttribute(o,a),this._$Em=null}}_$AK(e,t){const r=this.constructor,o=r._$Eh.get(e);if(void 0!==o&&this._$Em!==o){const a=r.getPropertyOptions(o),i="function"==typeof a.converter?{fromAttribute:a.converter}:void 0!==a.converter?.fromAttribute?a.converter:De;this._$Em=o;const u=i.fromAttribute(t,a.type);this[o]=u??this._$Ej?.get(o)??u,this._$Em=null}}requestUpdate(e,t,r,o=false,a){if(void 0!==e){const i=this.constructor;if(false===o&&(a=this[e]),r??=i.getPropertyOptions(e),!((r.hasChanged??It)(a,t)||r.useDefault&&r.reflect&&a===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,r))))return;this.C(e,t,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:o,wrapped:a},i){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),true!==a||void 0!==i)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),true===o&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(t){Promise.reject(t)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[o,a]of this._$Ep)this[o]=a;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[o,a]of r){const{wrapped:i}=a,u=this[o];true!==i||this._$AL.has(o)||void 0===u||this.C(o,void 0,a,u)}}let e=false;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=false,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return true}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[I("elementProperties")]=new Map,w[I("finalized")]=new Map,Wn?.({ReactiveElement:w}),(le.reactiveElementVersions??=[]).push("2.1.2");var Ke=globalThis;var Ft=n=>n;var ce=Ke.trustedTypes;var Vt=ce?ce.createPolicy("lit-html",{createHTML:n=>n}):void 0;var Xt="$lit$";var k=`lit$${Math.random().toFixed(9).slice(2)}$`;var Yt="?"+k;var Kn=`<${Yt}>`;var P=document;var V=()=>P.createComment("");var j=n=>null===n||"object"!=typeof n&&"function"!=typeof n;var Ge=Array.isArray;var Gn=n=>Ge(n)||"function"==typeof n?.[Symbol.iterator];var Ie="[ 	\n\f\r]";var F=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var jt=/-->/g;var Bt=/>/g;var A=RegExp(`>|${Ie}(?:([^\\s"'>=/]+)(${Ie}*=${Ie}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Wt=/'/g;var Kt=/"/g;var Jt=/^(?:script|style|textarea|title)$/i;var Xe=n=>(e,...t)=>({_$litType$:n,strings:e,values:t});var s=Xe(1);var zr=Xe(2);var Tr=Xe(3);var z=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var Gt=new WeakMap;var E=P.createTreeWalker(P,129);function Qt(n,e){if(!Ge(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Vt?Vt.createHTML(e):e}var Xn=(n,e)=>{const t=n.length-1,r=[];let o,a=2===e?"<svg>":3===e?"<math>":"",i=F;for(let u=0;u<t;u++){const l=n[u];let d,p,h=-1,m=0;for(;m<l.length&&(i.lastIndex=m,p=i.exec(l),null!==p);)m=i.lastIndex,i===F?"!--"===p[1]?i=jt:void 0!==p[1]?i=Bt:void 0!==p[2]?(Jt.test(p[2])&&(o=RegExp("</"+p[2],"g")),i=A):void 0!==p[3]&&(i=A):i===A?">"===p[0]?(i=o??F,h=-1):void 0===p[1]?h=-2:(h=i.lastIndex-p[2].length,d=p[1],i=void 0===p[3]?A:'"'===p[3]?Kt:Wt):i===Kt||i===Wt?i=A:i===jt||i===Bt?i=F:(i=A,o=void 0);const y=i===A&&n[u+1].startsWith("/>")?" ":"";a+=i===F?l+Kn:h>=0?(r.push(d),l.slice(0,h)+Xt+l.slice(h)+k+y):l+k+(-2===h?u:y)}return[Qt(n,a+(n[t]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),r]};var B=class n{constructor({strings:e,_$litType$:t},r){let o;this.parts=[];let a=0,i=0;const u=e.length-1,l=this.parts,[d,p]=Xn(e,t);if(this.el=n.createElement(d,r),E.currentNode=this.el.content,2===t||3===t){const h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;null!==(o=E.nextNode())&&l.length<u;){if(1===o.nodeType){if(o.hasAttributes())for(const h of o.getAttributeNames())if(h.endsWith(Xt)){const m=p[i++],y=o.getAttribute(h).split(k),S=/([.?@])?(.*)/.exec(m);l.push({type:1,index:a,name:S[2],strings:y,ctor:"."===S[1]?Ve:"?"===S[1]?je:"@"===S[1]?Be:M}),o.removeAttribute(h)}else h.startsWith(k)&&(l.push({type:6,index:a}),o.removeAttribute(h));if(Jt.test(o.tagName)){const h=o.textContent.split(k),m=h.length-1;if(m>0){o.textContent=ce?ce.emptyScript:"";for(let y=0;y<m;y++)o.append(h[y],V()),E.nextNode(),l.push({type:2,index:++a});o.append(h[m],V())}}}else if(8===o.nodeType)if(o.data===Yt)l.push({type:2,index:a});else{let h=-1;for(;-1!==(h=o.data.indexOf(k,h+1));)l.push({type:7,index:a}),h+=k.length-1}a++}}static createElement(e,t){const r=P.createElement("template");return r.innerHTML=e,r}};function L(n,e,t=n,r){if(e===z)return e;let o=void 0!==r?t._$Co?.[r]:t._$Cl;const a=j(e)?void 0:e._$litDirective$;return o?.constructor!==a&&(o?._$AO?.(false),void 0===a?o=void 0:(o=new a(n),o._$AT(n,t,r)),void 0!==r?(t._$Co??=[])[r]=o:t._$Cl=o),void 0!==o&&(e=L(n,o._$AS(n,e.values),o,r)),e}var Fe=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:r}=this._$AD,o=(e?.creationScope??P).importNode(t,true);E.currentNode=o;let a=E.nextNode(),i=0,u=0,l=r[0];for(;void 0!==l;){if(i===l.index){let d;2===l.type?d=new W(a,a.nextSibling,this,e):1===l.type?d=new l.ctor(a,l.name,l.strings,this,e):6===l.type&&(d=new We(a,this,e)),this._$AV.push(d),l=r[++u]}i!==l?.index&&(a=E.nextNode(),i++)}return E.currentNode=P,o}p(e){let t=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}};var W=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,o){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??true}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=L(this,e,t),j(e)?e===c||null==e||""===e?(this._$AH!==c&&this._$AR(),this._$AH=c):e!==this._$AH&&e!==z&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):Gn(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==c&&j(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:r}=e,o="number"==typeof r?this._$AC(e):(void 0===r.el&&(r.el=B.createElement(Qt(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(t);else{const a=new Fe(o,this),i=a.u(this.options);a.p(t),this.T(i),this._$AH=a}}_$AC(e){let t=Gt.get(e.strings);return void 0===t&&Gt.set(e.strings,t=new B(e)),t}k(e){Ge(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let r,o=0;for(const a of e)o===t.length?t.push(r=new n(this.O(V()),this.O(V()),this,this.options)):r=t[o],r._$AI(a),o++;o<t.length&&(this._$AR(r&&r._$AB.nextSibling,o),t.length=o)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(false,true,t);e!==this._$AB;){const r=Ft(e).nextSibling;Ft(e).remove(),e=r}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}};var M=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,o,a){this.type=1,this._$AH=c,this._$AN=void 0,this.element=e,this.name=t,this._$AM=o,this.options=a,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=c}_$AI(e,t=this,r,o){const a=this.strings;let i=false;if(void 0===a)e=L(this,e,t,0),i=!j(e)||e!==this._$AH&&e!==z,i&&(this._$AH=e);else{const u=e;let l,d;for(e=a[0],l=0;l<a.length-1;l++)d=L(this,u[r+l],t,l),d===z&&(d=this._$AH[l]),i||=!j(d)||d!==this._$AH[l],d===c?e=c:e!==c&&(e+=(d??"")+a[l+1]),this._$AH[l]=d}i&&!o&&this.j(e)}j(e){e===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}};var Ve=class extends M{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===c?void 0:e}};var je=class extends M{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==c)}};var Be=class extends M{constructor(e,t,r,o,a){super(e,t,r,o,a),this.type=5}_$AI(e,t=this){if((e=L(this,e,t,0)??c)===z)return;const r=this._$AH,o=e===c&&r!==c||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,a=e!==c&&(r===c||o);o&&this.element.removeEventListener(this.name,this,r),a&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}};var We=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){L(this,e)}};var Yn=Ke.litHtmlPolyfillSupport;Yn?.(B,W),(Ke.litHtmlVersions??=[]).push("3.3.3");var en=(n,e,t)=>{const r=t?.renderBefore??e;let o=r._$litPart$;if(void 0===o){const a=t?.renderBefore??null;r._$litPart$=o=new W(e.insertBefore(V(),a),a,void 0,t??{})}return o._$AI(n),o};var Ye=globalThis;var x=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=en(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return z}};x._$litElement$=true,x["finalized"]=true,Ye.litElementHydrateSupport?.({LitElement:x});var Jn=Ye.litElementPolyfillSupport;Jn?.({LitElement:x});(Ye.litElementVersions??=[]).push("4.2.2");var T=class extends Event{constructor(e,t,r,o){super("context-request",{bubbles:true,composed:true}),this.context=e,this.contextTarget=t,this.callback=r,this.subscribe=o??false}};function O(n){return n}var $=class{constructor(e,t,r,o){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(a,i)=>{this.unsubscribe&&(this.unsubscribe!==i&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=a,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(a,i)),this.unsubscribe=i},this.host=e,void 0!==t.context){const a=t;this.context=a.context,this.callback=a.callback,this.subscribe=a.subscribe??false}else this.context=t,this.callback=r,this.subscribe=o??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new T(this.context,this.host,this.t,this.subscribe))}};var tn=Ne`
  :host {
    display: block;
    --_hy-text: var(--hydronicus-text, var(--primary-text-color, #1c1c1c));
    --_hy-text-muted: var(--hydronicus-text-muted, var(--secondary-text-color, #5f6368));
    --_hy-surface: var(--hydronicus-surface, var(--ha-card-background, var(--card-background-color, #fff)));
    --_hy-surface-raised: var(--hydronicus-surface-raised, color-mix(in srgb, var(--_hy-text) 4%, transparent));
    --_hy-line: var(--hydronicus-line, var(--divider-color, color-mix(in srgb, var(--_hy-text) 13%, transparent)));
    --_hy-accent: var(--hydronicus-accent, var(--primary-color, #03a9f4));
    --_hy-heating: var(--hydronicus-heating-color, var(--state-climate-heat-color, #ff8100));
    --_hy-cooling: var(--hydronicus-cooling-color, var(--state-climate-cool-color, #2b9af9));
    --_hy-idle: var(--hydronicus-idle-color, var(--primary-color, #03a9f4));
    --_hy-attention: var(--hydronicus-attention-color, var(--error-color, #db4437));
    --_hy-success: var(--hydronicus-success-color, var(--success-color, #43a047));
    --_hy-warning: var(--hydronicus-warning-color, var(--warning-color, #ffa600));
    --_hy-danger: var(--hydronicus-danger-color, var(--error-color, #db4437));
    --_hy-radius: var(--hydronicus-radius, var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px)));
    --_hy-radius-inner: var(--hydronicus-radius-inner, var(--ha-border-radius-md, 8px));
    --_hy-radius-control: var(--hydronicus-radius-control, var(--_hy-radius-inner));
    --_hy-card-border: var(--hydronicus-card-border, var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0)));
    --_hy-card-shadow: var(--hydronicus-card-shadow, var(--ha-card-box-shadow, none));
    --_hy-tile-border: var(--hydronicus-tile-border, 1px solid var(--_hy-line));
    --_hy-tile-shadow: var(--hydronicus-tile-shadow, none);
    --_hy-tile-active-shadow: var(--hydronicus-tile-active-shadow, var(--_hy-tile-shadow));
    --_hy-control-border: var(--hydronicus-control-border, 1px solid var(--_hy-line));
    --_hy-control-shadow: var(--hydronicus-control-shadow, none);
    --_hy-control-surface: var(--hydronicus-control-surface, var(--_hy-surface-raised));
    --_hy-control-color: var(--hydronicus-control-color, var(--_hy-text));
    --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-accent) 14%, transparent));
    --_hy-selected-color: var(--hydronicus-selected-color, var(--_hy-text));
    --_hy-font-body: var(--hydronicus-font-body, var(--ha-font-family-body, inherit));
    --_hy-font-display: var(--hydronicus-font-display, var(--_hy-font-body));
    --_hy-font-weight-display: var(--hydronicus-font-weight-display, var(--ha-font-weight-medium, 500));
    --_hy-ambient-opacity: var(--hydronicus-ambient-opacity, 0);
    --_hy-glass-blur: var(--hydronicus-glass-blur, 0px);
    --_hy-glass-opacity: var(--hydronicus-glass-opacity, 100%);
    --_hy-flow-duration: var(--hydronicus-flow-duration, 2.2s);
    --_hy-ambient-duration: var(--hydronicus-ambient-duration, 16s);
    /* Internal: state colours as text, mixed toward the text colour so small labels stay legible. */
    --_hy-warning-ink: color-mix(in srgb, var(--_hy-warning) 52%, var(--_hy-text));
    --_hy-success-ink: color-mix(in srgb, var(--_hy-success) 70%, var(--_hy-text));
    --_hy-danger-ink: color-mix(in srgb, var(--_hy-danger) 85%, var(--_hy-text));
    /* Internal: the colour of the current state, and the inline-start side. */
    --_hy-state: var(--_hy-idle);
    --_hy-inline-start: left;
    font-variant-numeric: tabular-nums;
  }

  :host(:dir(rtl)) {
    --_hy-inline-start: right;
  }

  ha-card {
    display: block;
    box-sizing: border-box;
    container-type: inline-size;
    overflow: hidden;
    position: relative;
    isolation: isolate;
    height: 100%;
    border: var(--_hy-card-border);
    border-radius: var(--_hy-radius);
    box-shadow: var(--_hy-card-shadow);
    color: var(--_hy-text);
    font-family: var(--_hy-font-body);
    background: color-mix(in srgb, var(--_hy-surface) var(--_hy-glass-opacity), transparent);
    /* The glass blur adds to a backdrop filter the theme gives every card. */
    -webkit-backdrop-filter: blur(var(--_hy-glass-blur)) var(--ha-card-backdrop-filter,);
    backdrop-filter: blur(var(--_hy-glass-blur)) var(--ha-card-backdrop-filter,);
    padding: var(--ha-space-4, 16px);
  }

  ha-card::before {
    content: "";
    position: absolute;
    z-index: -1;
    inset: -35%;
    pointer-events: none;
    background:
      radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--_hy-state) 16%, transparent) 0, transparent 32%),
      radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--_hy-accent) 9%, transparent) 0, transparent 30%);
    /* The ambient glow is decorative and off unless a theme turns it on. */
    opacity: var(--_hy-ambient-opacity);
    transform: translate3d(-2%, -1%, 0) scale(1.02);
    animation: hydronicus-ambient var(--_hy-ambient-duration) ease-in-out infinite alternate;
  }

  ha-card[data-visual="heating"] { --_hy-state: var(--_hy-heating); }
  ha-card[data-visual="cooling"] { --_hy-state: var(--_hy-cooling); }
  ha-card[data-visual="attention"] { --_hy-state: var(--_hy-attention); }
  ha-card.compact { padding: var(--ha-space-3, 12px); }

  .visually-hidden {
    position: absolute;
    inline-size: 1px;
    block-size: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .header, .row, .path-head, .section-head, .plant-heading, .status-line, .boundary-copy { display: flex; align-items: center; gap: 0.65rem; }
  .header { justify-content: space-between; align-items: flex-start; gap: 1.2rem; }
  .header-copy { min-inline-size: 0; }
  h2, h3, h4, p, ul, ol { margin: 0; }
  ul, ol { padding: 0; list-style: none; }
  h2, h3, h4, summary { font-family: var(--_hy-font-display); font-weight: var(--_hy-font-weight-display); }
  h2 { font-size: var(--ha-font-size-xl, 1.25rem); line-height: 1.3; overflow-wrap: anywhere; }
  h3 { font-size: var(--ha-font-size-m, 0.95rem); }
  h4 { font-size: var(--ha-font-size-m, 0.9rem); }
  .muted, .meta { color: var(--_hy-text-muted); font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.45; }
  .eyebrow { margin-block-end: 0.12rem; color: color-mix(in srgb, var(--_hy-state) 65%, var(--_hy-text)); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
  .plant-heading { align-items: flex-start; }
  .plant-mark {
    position: relative;
    flex: 0 0 2.7rem;
    inline-size: 2.7rem;
    block-size: 2.7rem;
    border-radius: var(--_hy-radius-inner);
    background: color-mix(in srgb, var(--_hy-state) 14%, transparent);
  }
  .plant-mark::before {
    content: "";
    position: absolute;
    inset: 0.58rem;
    border: 2px solid color-mix(in srgb, var(--_hy-state) 30%, transparent);
    border-block-start-color: var(--_hy-state);
    border-radius: 50%;
    animation: hydronicus-spin 3.8s linear infinite;
  }
  .plant-mark::after {
    content: "";
    position: absolute;
    inset: 0;
    margin: auto;
    inline-size: 0.42rem;
    block-size: 0.42rem;
    border-radius: 50%;
    background: var(--_hy-state);
  }
  button.link {
    min-block-size: 0;
    border: 0;
    border-radius: 0.3rem;
    background: none;
    box-shadow: none;
    padding: 0;
    color: inherit;
    font: inherit;
    text-align: start;
    text-decoration: underline dotted color-mix(in srgb, currentColor 40%, transparent);
    text-underline-offset: 0.2em;
  }
  button.link:hover { background: none; text-decoration-color: var(--_hy-accent); }
  .status-line { flex-wrap: wrap; margin-block-start: 0.48rem; gap: 0.35rem; }
  .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 600; }
  .status-dot { inline-size: 0.45rem; block-size: 0.45rem; border-radius: 50%; background: var(--_hy-state); animation: hydronicus-pulse 2.8s ease-out infinite; }
  .health { font-size: 0.78rem; font-weight: 600; color: var(--_hy-warning-ink); }
  .health[data-health="unavailable"] { color: var(--_hy-danger-ink); }
  .mode-detail { border-inline-start: 1px solid var(--_hy-line); padding-inline-start: 0.55rem; }
  .source-line { margin-block-start: 0.35rem; }
  .source-line strong { color: var(--_hy-text); font-weight: 600; }
  .badge, .phase, .state { border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.72rem; line-height: 1.2; white-space: nowrap; }
  .badge { font-weight: 700; letter-spacing: 0.02em; background: color-mix(in srgb, var(--_hy-warning) 12%, transparent); }
  .badge.dry-run, .state.proposed { color: var(--_hy-warning-ink); }
  .badge.mixed, .badge.live, .state.blocked, .state.mismatch { color: var(--_hy-danger-ink); }
  .badge.mixed, .badge.live { background: color-mix(in srgb, var(--_hy-danger) 10%, transparent); }
  .phase.off { color: var(--_hy-text-muted); }
  .badge.active, .state.active, .state.ready { color: var(--_hy-success-ink); }
  .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
  .mode-control { display: flex; align-items: center; min-block-size: 2.5rem; box-sizing: border-box; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); color: var(--_hy-control-color); padding-inline-start: 0.62rem; }
  .control-label { color: var(--_hy-text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  button, select { min-block-size: 2.5rem; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); color: var(--_hy-control-color); font: inherit; padding: 0.38rem 0.7rem; transition: border-color 180ms ease, background-color 180ms ease, transform 120ms ease; }
  .mode-control select { border: 0; background: transparent; box-shadow: none; min-block-size: 2.4rem; }
  button { cursor: pointer; }
  button:hover, select:hover { border-color: color-mix(in srgb, var(--_hy-state) 46%, var(--_hy-line)); background: color-mix(in srgb, var(--_hy-text) 8%, transparent); }
  button:active { transform: translateY(1px); }
  button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
  button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--_hy-accent); outline-offset: 2px; }
  .shutdown { position: relative; overflow: hidden; color: var(--_hy-danger-ink); touch-action: none; user-select: none; -webkit-user-select: none; }
  .shutdown.quiet { color: var(--_hy-text-muted); }
  .shutdown.quiet:hover, .shutdown.quiet:focus-visible, .shutdown.quiet.is-holding { color: var(--_hy-danger-ink); }
  .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--_hy-danger) 18%, transparent); transform: scaleX(0); transform-origin: var(--_hy-inline-start); }
  .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
  .button-label { position: relative; z-index: 1; }
  .hold-progress { flex-basis: 100%; text-align: end; font-size: 0.7rem; color: var(--_hy-danger-ink); }
  .alert, .error, .boundary, .notice { margin-block-start: 0.9rem; border: 1px solid var(--_hy-line); border-radius: var(--_hy-radius-inner); background: var(--_hy-surface-raised); padding: 0.68rem 0.75rem; }
  .alert, .notice, .action-error { position: relative; overflow: hidden; padding-inline-start: 0.9rem; }
  .alert::before, .notice::before, .action-error::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--_hy-warning); }
  .alert.error::before, .action-error::before { background: var(--_hy-danger); }
  .action-error { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-block-start: 0.9rem; border: 1px solid color-mix(in srgb, var(--_hy-danger) 40%, var(--_hy-line)); border-radius: var(--_hy-radius-inner); padding-block: 0.4rem; padding-inline-end: 0.4rem; color: var(--_hy-danger-ink); font-size: 0.85rem; }
  .action-error button { min-block-size: 2.2rem; color: inherit; }
  .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
  .boundary-orb { display: grid; place-items: center; inline-size: 1.75rem; block-size: 1.75rem; border-radius: var(--_hy-radius-inner); background: color-mix(in srgb, var(--_hy-state) 14%, transparent); color: var(--_hy-state); }
  .boundary-orb::before { content: ""; inline-size: 0.55rem; block-size: 0.55rem; border: 2px solid currentColor; border-radius: 50%; }
  .boundary-copy { min-inline-size: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
  .boundary-copy strong { font-size: 0.82rem; font-weight: 600; }
  section { margin-block-start: 1.05rem; }
  .section-head { flex-wrap: wrap; justify-content: space-between; row-gap: 0.2rem; margin-block-end: 0.5rem; }
  /* A long section note wraps below the title instead of squeezing it. */
  .section-head > .meta { margin-inline-start: auto; }
  .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
  .zone, .path, .actuator, details { border: var(--_hy-tile-border); border-radius: var(--_hy-radius-inner); background: var(--_hy-surface-raised); box-shadow: var(--_hy-tile-shadow); }
  .zone, .path, .actuator { padding: 0.72rem; }
  .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
  .zone::before { content: ""; position: absolute; inset-block-start: 0; inset-inline: 0; block-size: 2px; background: var(--_hy-state); opacity: 0; transform: scaleX(0.35); transform-origin: var(--_hy-inline-start); transition: opacity 220ms ease, transform 380ms ease; }
  .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
  /* A Zone without demand is idle, whatever the Plant around it is doing. */
  .zone[data-demand-kind="none"] { --_hy-state: var(--_hy-idle); }
  .zone[data-demand-kind="heating"] { --_hy-state: var(--_hy-heating); }
  .zone[data-demand-kind="cooling"] { --_hy-state: var(--_hy-cooling); }
  /* An active tile's border follows its own state colour, so it resolves on the tile. */
  .zone[data-demand="true"] { --_hy-tile-active-border: var(--hydronicus-tile-active-border, 1px solid color-mix(in srgb, var(--_hy-state) 30%, var(--_hy-line))); background: color-mix(in srgb, var(--_hy-state) 7%, transparent); }
  .path[data-flowing="true"] { --_hy-tile-active-border: var(--hydronicus-tile-active-border, var(--_hy-tile-border)); }
  .zone[data-demand="true"], .path[data-flowing="true"] { border: var(--_hy-tile-active-border); box-shadow: var(--_hy-tile-active-shadow); }
  .zone[data-hvac-mode="off"] .metric.target { background: transparent; }
  .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--_hy-danger) 34%, var(--_hy-line)); }
  .row { justify-content: space-between; align-items: baseline; }
  .zone-title { min-inline-size: 0; overflow-wrap: anywhere; }
  .zone-owner { margin-block-start: 0.12rem; }
  .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin-block: 0.65rem 0.5rem; }
  .metric { min-inline-size: 0; border: 1px solid color-mix(in srgb, var(--_hy-line) 72%, transparent); border-radius: var(--_hy-radius-inner); padding: 0.52rem 0.58rem; }
  .metric.target { background: color-mix(in srgb, var(--_hy-state) 8%, transparent); }
  .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 600; letter-spacing: -0.02em; }
  .metric-unit { margin-inline-start: 0.15rem; color: var(--_hy-text-muted); font-size: 0.75rem; }
  .metric-label { display: block; margin-block-start: 0.06rem; color: var(--_hy-text-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; }
  /*
   * One compact line per area: a name that shortens, then readings in aligned
   * columns. The name column is only as wide as the longest name, so in a wide
   * tile the readings stay next to their names instead of at the far edge.
   */
  .area-list { display: grid; grid-template-columns: minmax(0, max-content) auto; justify-content: start; column-gap: 1rem; margin-block-end: 0.3rem; font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.45; }
  .area-list[data-humidity="true"] { grid-template-columns: minmax(0, max-content) auto auto; }
  .area { display: grid; grid-column: 1 / -1; grid-template-columns: subgrid; align-items: baseline; padding-block: 0.2rem; border-block-start: 1px solid color-mix(in srgb, var(--_hy-line) 60%, transparent); }
  .area:first-child { border-block-start: 0; }
  ha-card.compact .area { padding-block: 0.1rem; }
  .area-name { min-inline-size: 0; overflow: hidden; color: var(--_hy-text-muted); text-overflow: ellipsis; white-space: nowrap; }
  .area-name button.link { max-inline-size: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
  .area-value { text-align: end; white-space: nowrap; }
  /* A missing area's tag takes the place of its readings. */
  .area-missing { grid-column: 2 / -1; justify-self: end; border: 1px solid color-mix(in srgb, var(--_hy-warning) 34%, var(--_hy-line)); border-radius: 999px; padding: 0 0.42rem; color: var(--_hy-warning-ink); font-size: 0.7rem; line-height: 1.5; white-space: nowrap; }
  .zone-alerts { display: grid; gap: 0.35rem; margin-block: 0.45rem 0.1rem; }
  .zone-alerts > .alert { margin-block-start: 0; padding-block: 0.42rem; font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.4; }
  .zone-note { margin-block-start: 0.28rem; }
  .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.45rem; }
  .diagnostic-chip { border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--_hy-text-muted); font-size: 0.7rem; }
  .diagnostic-chip.warning { color: var(--_hy-warning-ink); border-color: color-mix(in srgb, var(--_hy-warning) 30%, var(--_hy-line)); }
  .diagnostic-chip.danger { color: var(--_hy-danger-ink); border-color: color-mix(in srgb, var(--_hy-danger) 30%, var(--_hy-line)); }
  .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-block-start: 0.38rem; color: var(--_hy-warning-ink); }
  /* Equal segments; a narrow tile wraps them into even rows, and the corner stops at a one-row pill so two rows stay a rounded box. */
  .hvac-modes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 4.75rem), 1fr)); gap: 0.25rem; margin-block-start: 0.62rem; padding: 0.2rem; border: var(--_hy-control-border); border-radius: min(var(--_hy-radius-control), 1.35rem); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); }
  .hvac-mode { min-inline-size: 0; min-block-size: 2.2rem; padding-inline: 0.4rem; border: 1px solid transparent; border-radius: max(0px, calc(min(var(--_hy-radius-control), 1.35rem) - 0.2rem)); background: transparent; box-shadow: none; font-size: 0.8rem; white-space: nowrap; }
  /* A selected segment keeps its per-mode tint unless the theme sets a selected background. */
  .hvac-mode[data-mode="heat"] { --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-heating) 16%, transparent)); }
  .hvac-mode[data-mode="cool"] { --_hy-selected-background: var(--hydronicus-selected-background, color-mix(in srgb, var(--_hy-cooling) 16%, transparent)); }
  .hvac-mode[data-mode="off"] { --_hy-selected-background: var(--hydronicus-selected-background, var(--_hy-surface-raised)); }
  [aria-pressed="true"] { background: var(--_hy-selected-background); color: var(--_hy-selected-color); }
  .hvac-mode[aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-accent) 50%, var(--_hy-line)); background: var(--_hy-selected-background); font-weight: 600; }
  .hvac-mode[data-mode="heat"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-heating) 55%, var(--_hy-line)); }
  .hvac-mode[data-mode="cool"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--_hy-cooling) 55%, var(--_hy-line)); }
  .hvac-mode[data-mode="off"][aria-pressed="true"] { border-color: var(--_hy-line); }
  .zone-actions { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-block-start: 0.45rem; }
  .zone-actions button { min-inline-size: 2.75rem; }
  .preset { flex: 1 1 7rem; min-inline-size: 7rem; }
  .path-list, .actuator-list { display: grid; gap: 0.55rem; }
  .path { overflow: hidden; }
  .path-head { justify-content: space-between; flex-wrap: wrap; }
  .path-heading { display: flex; align-items: center; gap: 0.42rem; min-inline-size: 0; }
  .path-heading::before { content: ""; flex: 0 0 auto; inline-size: 0.43rem; block-size: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--_hy-text-muted) 55%, transparent); }
  /* A path takes the colour of its own Zone's demand. */
  /* A path of a Zone without demand is idle, even where a shared pump runs for another Zone. */
  .path[data-demand-kind="none"] { --_hy-state: var(--_hy-idle); }
  .path[data-demand-kind="heating"] { --_hy-state: var(--_hy-heating); }
  .path[data-demand-kind="cooling"] { --_hy-state: var(--_hy-cooling); }
  .path[data-flowing="true"] .path-heading::before { background: var(--_hy-state); animation: hydronicus-pulse 2.4s ease-out infinite; }
  .path[data-status="blocked"] .path-heading::before { background: var(--_hy-danger); }
  .path-track { display: flex; align-items: stretch; margin-block-start: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding-block: 0.08rem 0.25rem; padding-inline: 0.03rem; scroll-snap-type: inline proximity; scrollbar-width: thin; }
  .path-step { display: contents; }
  .node { display: grid; align-content: start; box-sizing: border-box; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-inline-size: 0; border: 1px solid var(--_hy-line); border-radius: calc(var(--_hy-radius-inner) * 0.75); padding: 0.48rem 0.52rem; font-size: 0.76rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, background-color 220ms ease; }
  .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--_hy-state) 34%, var(--_hy-line)); background: color-mix(in srgb, var(--_hy-state) 8%, transparent); }
  .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--_hy-danger) 36%, var(--_hy-line)); }
  .node-kind { color: var(--_hy-text-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .node-name { margin-block-start: 0.18rem; font-weight: 600; line-height: 1.25; }
  .node-state { display: flex; align-items: center; gap: 0.28rem; margin-block-start: 0.3rem; color: var(--_hy-text-muted); font-size: 0.68rem; }
  .node-state::before { content: ""; inline-size: 0.3rem; block-size: 0.3rem; border-radius: 50%; background: currentColor; }
  .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--_hy-state) 60%, var(--_hy-text)); }
  /* A connector grows only to a short cap, so a path reads as a compact chain from the start at any width. */
  .flow-link { position: relative; flex: 1 0 clamp(1rem, 4cqi, 2.4rem); min-inline-size: 1rem; max-inline-size: 2.4rem; align-self: center; block-size: 2px; margin-inline: 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--_hy-text-muted) 24%, transparent); }
  :host(:dir(rtl)) .flow-link { transform: scaleX(-1); }
  .flow-link::before { content: ""; position: absolute; inset-inline-end: 0; inset-block-start: 50%; inline-size: 0.34rem; block-size: 0.34rem; border-block-start: 1px solid var(--_hy-text-muted); border-inline-end: 1px solid var(--_hy-text-muted); transform: translateY(-50%) rotate(45deg); }
  .flow-link::after { content: ""; position: absolute; inset-block: -1px; inset-inline-start: 0; inline-size: 58%; background: linear-gradient(90deg, transparent, var(--_hy-state), transparent); opacity: 0; transform: translateX(-120%); }
  .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--_hy-state) 24%, transparent); }
  .path[data-flowing="true"] .flow-link::before { border-color: var(--_hy-state); }
  .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--_hy-flow-duration) linear infinite; }
  .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--_hy-danger) 30%, transparent); }
  .path-problem { margin-block-start: 0.5rem; color: var(--_hy-danger-ink); }
  .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
  .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
  .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.48rem; }
  .consumer-chip { max-inline-size: 100%; border: 1px solid var(--_hy-line); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--_hy-text-muted); font-size: 0.7rem; overflow-wrap: anywhere; }
  .consumer-chip strong { color: var(--_hy-text); font-weight: 600; }
  details { overflow: hidden; padding: 0.62rem 0.72rem; }
  details + details { margin-block-start: 0.45rem; }
  summary { cursor: pointer; font-size: 0.85rem; }
  details[open] summary { margin-block-end: 0.25rem; }
  details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
  .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding-block: 0.48rem; border-block-start: 1px solid var(--_hy-line); font-size: 0.82rem; }
  .operation:first-of-type { border-block-start: 0; }
  .operation-marker { inline-size: 0.4rem; block-size: 0.4rem; margin-block-start: 0.35rem; border-radius: 50%; background: var(--_hy-text-muted); }
  .operation[data-result="proposed"] .operation-marker { background: var(--_hy-warning); }
  .operation[data-result="executed"] .operation-marker { background: var(--_hy-success); }
  .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--_hy-danger); }
  .operation-copy { min-inline-size: 0; }
  .empty-state { padding: 0.8rem; border: 1px dashed var(--_hy-line); border-radius: var(--_hy-radius-inner); text-align: center; }
  /* A Zone card is the Zone tile itself: the card frame replaces the tile's. */
  ha-card.zone-card { padding: 0; }
  ha-card.zone-card > .zone { border: 0; border-radius: inherit; box-shadow: none; }
  ha-card.zone-card > .zone:not([data-demand="true"]) { background: transparent; }
  ha-card.zone-card.compact > .zone { padding: 0.55rem; }
  ha-card.zone-card > .notice, ha-card.zone-card > .action-error { margin-block-start: 0.72rem; margin-inline: 0.72rem; }
  h2.zone-title { font-size: var(--ha-font-size-m, 0.9rem); }
  .state-card { display: grid; gap: 0.6rem; }
  .loading-card { min-block-size: 12rem; }
  .loading-head { display: flex; align-items: center; gap: 0.65rem; }
  .loading-mark, .skeleton { background: linear-gradient(105deg, var(--_hy-surface-raised) 20%, color-mix(in srgb, var(--_hy-text) 10%, transparent) 38%, var(--_hy-surface-raised) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
  .loading-mark { inline-size: 2.7rem; block-size: 2.7rem; border-radius: var(--_hy-radius-inner); }
  .skeleton { inline-size: min(16rem, 62cqi); block-size: 0.72rem; border-radius: 999px; }
  .skeleton.short { inline-size: min(10rem, 42cqi); margin-block-start: 0.45rem; }
  .loading-panel { block-size: 4.2rem; margin-block-start: 0.9rem; border: 1px solid var(--_hy-line); border-radius: var(--_hy-radius-inner); }
  @container (max-width: 680px) {
    .header { display: block; }
    .controls { justify-content: flex-start; margin-block-start: 0.7rem; }
    .hold-progress { text-align: start; }
  }
  @container (max-width: 440px) {
    .zone-grid { grid-template-columns: 1fr; }
    .mode-detail { flex-basis: 100%; border-inline-start: 0; padding-inline-start: 0; }
    .boundary-copy { display: block; }
    .boundary-copy .control-label { display: block; margin-block-end: 0.12rem; }
    .section-head { align-items: flex-start; }
    .section-head > .meta { text-align: end; }
  }
  @media (prefers-reduced-motion: reduce) {
    ha-card::before, .plant-mark::before, .status-dot, .path-heading::before, .path[data-flowing="true"] .flow-link::after, details[open] .operation, .loading-mark, .skeleton { animation: none !important; }
    button, select, .zone, .node { transition-duration: 0.01ms !important; }
    .path[data-flowing="true"] .flow-link::after { opacity: 0.65; transform: translateX(40%); }
    .shutdown.is-holding::after { animation: none; transform: scaleX(1); }
  }

  @keyframes hydronicus-ambient {
    from { transform: translate3d(-2%, -1%, 0) scale(1.02); }
    to { transform: translate3d(3%, 2%, 0) scale(1.08); }
  }
  @keyframes hydronicus-spin { to { transform: rotate(360deg); } }
  @keyframes hydronicus-pulse {
    0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--_hy-state) 38%, transparent); }
    58%, 100% { box-shadow: 0 0 0 0.48rem transparent; }
  }
  @keyframes hydronicus-flow {
    from { transform: translateX(-120%); }
    to { transform: translateX(230%); }
  }
  @keyframes hydronicus-hold {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }
  @keyframes hydronicus-reveal {
    from { opacity: 0; transform: translateY(-3px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes hydronicus-shimmer {
    from { background-position: 100% 0; }
    to { background-position: -100% 0; }
  }
`;var er=O("hassConnection");var tr=O("hassApi");var nr=O("hassConfig");var rr=O("hassInternationalization");var q=class extends x{static properties={preview:{type:Boolean},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_plant:{state:true},_actionError:{state:true}};static styles=tn;_hass;_callService;_fromContext=new Set;_release;_followed;constructor(){super();this.preview=false;this._connection=void 0;this._unit=C;this._locale=void 0;this._localize=void 0;this._plant=R;this._actionError=null;new $(this,{context:er,subscribe:true,callback:e=>{this._fromContext.add("connection");this._connection=e?.connection}});new $(this,{context:tr,subscribe:true,callback:e=>{this._fromContext.add("api");this._callService=e?.callService}});new $(this,{context:nr,subscribe:true,callback:e=>{this._fromContext.add("config");this._unit=_e(e?.config?.unit_system)}});new $(this,{context:rr,subscribe:true,callback:e=>{this._fromContext.add("i18n");this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}})}set hass(e){this._hass=e;if(!this._fromContext.has("connection"))this._connection=e?.connection;if(!this._fromContext.has("api"))this._callService=e?(...t)=>e.callService(...t):void 0;if(!this._fromContext.has("config"))this._unit=_e(e?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}}get hass(){return this._hass}resetPlant(){this._plant=R;this._actionError=null}connectedCallback(){super.connectedCallback();this._follow()}disconnectedCallback(){this._unfollow();super.disconnectedCallback()}updated(e){super.updated(e);this._syncSelectValues();if(!this.isConnected)return;this._follow();if(this._connection&&(e.has("_connection")||this.preview))void _.load(this._connection)}_follow(){const e=this._connection;const t=this.plantId||void 0;const r=this._followed;if(r&&r.connection===e&&r.plantId===t)return;this._unfollow();if(!e||!t)return;this._followed={connection:e,plantId:t};this._release=H.subscribe(e,t,o=>{this._plant=o;this.plantStateChanged?.(o)})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._plant=R;this.plantStateChanged?.(R)}_syncSelectValues(){for(const e of this.renderRoot.querySelectorAll("select[data-value]")){const t=e.dataset.value??"";if(e.value!==t)e.value=t}}get renderContext(){return{unit:this._unit,locale:this._locale,localize:this._localize,moreInfo:e=>this.moreInfo(e),call:e=>this.call(e)}}moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:e}}))}call(e){const t=this._callService;if(!e||!t)return;t(e.domain,e.service,e.data,void 0,false).then(()=>{this._actionError=null},r=>{this._actionError=Z(r,"The Home Assistant action failed.");this.requestUpdate()})}dismissActionError=()=>{this._actionError=null}};function nn(n,e,t,r){const o=n.unit;if(e===null){return s`<div class=${r} part="metric"><span class="metric-value">--</span><span class="metric-label">${t}<span class="visually-hidden"> unavailable</span></span></div>`}return s`<div class=${r} part="metric"><span class="metric-value">${G(e,o,n.locale)}</span><span class="metric-unit">${o}</span><span class="metric-label">${t}</span></div>`}function rn(n,e,t,r){if(n===null){return s`<span class="area-value">--<span class="visually-hidden"> ${t?`${r} unavailable`:`no ${r} sensor`}</span></span>`}return s`<span class="area-value">${n}<span class="metric-unit">${e}</span></span>`}function or(n){return s`<li class="area" part="area" data-missing="true">
    <span class="area-name" dir="auto">${n.name}</span>
    <span class="area-missing" title="This area no longer exists in Home Assistant.">Missing<span class="visually-hidden"> - removed from Home Assistant</span></span>
  </li>`}function ar(n,e,t){if(e.missing)return or(e);const{unit:r,locale:o}=n;const a=e.temperature_entity_id??e.humidity_entity_id;const i=a?s`<button type="button" class="link" aria-haspopup="dialog" title=${`Show ${e.name} sensor details`} @click=${()=>n.moreInfo(a)}>${e.name}</button>`:e.name;return s`<li class="area" part="area">
    <span class="area-name" dir="auto">${i}</span>
    ${rn(e.temperature===null?null:G(e.temperature,r,o),r,e.temperature_entity_id,"temperature")}
    ${t?rn(e.humidity===null?null:g(e.humidity,o,0),"%",e.humidity_entity_id,"humidity"):c}
  </li>`}function ir(n,e){const t=Se(e);if(!t.length)return c;const r=t.some(o=>o.humidity!==null||o.humidity_entity_id!==null);return s`<ul class="area-list" data-humidity=${String(r)} aria-label="Areas">${t.map(o=>ar(n,o,r))}</ul>`}function sr(n,e){if(!e.length)return c;return s`<ul class="zone-alerts" aria-label=${`${n.name} alerts`}>${e.map(t=>{const r=t.severity==="error"||t.severity==="critical";return s`<li class="alert ${r?"error":""}" part="notice" data-severity=${t.severity} dir="auto"><strong>${Ae(t.code)}</strong><span> · ${t.message}</span></li>`})}</ul>`}function on(n,e,t){const r=kt(e,t,n.unit);if(r!==null)n.call(ht(e,r))}function lr(n,e,t){if(t===e.thermostat.hvac_mode)return;n.call(mt(e,t))}function cr(n,e,t){n.call(pt(e,t.target.value))}function de(n,e,t){const r=e.thermostat;const o=r.kind==="hydronicus";const a=Y(e);const i=a!=="none";const u=r.hvac_mode==="off";const{unit:l,locale:d,localize:p}=n;const h=g(xe(l),d,l===C?1:0);const m=r.control_entity_id;const y=Boolean(m)&&r.target_temperature!==null;const S=$t(e);const et=ke(e);const tt=r.hvac_mode?J(p,r.hvac_mode):null;const be=bt(e,p);const nt=e.blocked_reason&&!t.alerts.some(b=>b.message===e.blocked_reason)?e.blocked_reason:null;const rt=i?`${a==="cooling"?"Cooling":"Heating"} demand active`:u?"Thermostat off":"No demand";const ve=`zone-${e.id}`;const ot=m?s`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>n.moreInfo(m)}>${e.name}</button>`:e.name;const yn=t.headingLevel===2?s`<h2 class="zone-title" part="zone-title" id=${ve}>${ot}</h2>`:s`<h4 class="zone-title" part="zone-title" id=${ve}>${ot}</h4>`;return s`<article class="zone" part="zone" data-phase=${e.phase} data-hvac-mode=${r.hvac_mode??"unknown"} data-demand=${String(i)} data-demand-kind=${a} data-blocked=${String(e.blocked)} aria-labelledby=${ve}>
    <div class="row"><div>${yn}<p class="meta zone-owner">${o?"Hydronicus thermostat":`External thermostat \xB7 read-only${tt?` \xB7 ${tt}`:""}`}</p></div><span class=${`phase${be.kind==="blocked"?" state blocked":""}${be.kind==="off"?" off":""}`} part="badge">${be.label}</span></div>
    <div class="temperature-panel">
      ${nn(n,r.current_temperature,"Current","metric")}
      ${nn(n,r.target_temperature,"Target","metric target")}
    </div>
    ${ir(n,e)}
    ${sr(e,t.alerts)}
    <p class="meta zone-note" dir="auto">${o?rt:`${rt} \xB7 ${r.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Zone diagnostics">
      <li part="chip" class="diagnostic-chip" dir="auto">${g(e.sensor_status.usable,d,0)} sensor${e.sensor_status.usable===1?"":"s"} ready</li>
      ${e.sensor_status.optional_excluded?s`<li part="chip" class="diagnostic-chip warning" dir="auto">${g(e.sensor_status.optional_excluded,d,0)} optional excluded</li>`:c}
      ${e.sensor_status.required_blocking?s`<li part="chip" class="diagnostic-chip danger" dir="auto">${g(e.sensor_status.required_blocking,d,0)} required blocked</li>`:c}
      ${e.cooling.dew_point===null?c:s`<li part="chip" class="diagnostic-chip" dir="auto">Dew point ${G(e.cooling.dew_point,l,d)} ${l}</li>`}
      ${e.cooling.condensation_margin===null?c:s`<li part="chip" class="diagnostic-chip ${e.cooling.blocked?"danger":""}" dir="auto">Margin ${st(e.cooling.condensation_margin,l,d)} ${l}</li>`}
    </ul>
    ${r.preset&&r.preset!=="none"?s`<p class="meta zone-note" dir="auto">Preset: ${f(r.preset)}</p>`:c}
    ${nt?s`<p class="meta zone-note" dir="auto">${nt}</p>`:c}
    ${e.coupling_group_ids.length?s`<p class="meta coupling-note" dir="auto">Coupled delivery - this Zone shares hydraulic equipment.</p>`:c}
    ${o?s`${et.length?s`<div class="hvac-modes" part="control" role="group" aria-label=${`${e.name} HVAC mode`}>${et.map(b=>s`<button type="button" class="hvac-mode" part="segment" data-mode=${b} aria-pressed=${String(b===r.hvac_mode)} ?disabled=${!m} @click=${()=>lr(n,e,b)}>${J(p,b)}</button>`)}</div>`:c}
          <div class="zone-actions" part="controls">
            <button type="button" part="control" dir="ltr" ?disabled=${!y} aria-label=${`Decrease ${e.name} target by ${h} ${l}`} @click=${()=>on(n,e,-1)}>−${h}</button>
            <button type="button" part="control" dir="ltr" ?disabled=${!y} aria-label=${`Increase ${e.name} target by ${h} ${l}`} @click=${()=>on(n,e,1)}>+${h}</button>
            ${S.length?s`<select class="preset" part="control" data-value=${r.preset??"none"} aria-label=${`${e.name} preset`} ?disabled=${!m} @change=${b=>cr(n,e,b)}>${["none",...S].map(b=>s`<option value=${b}>${f(b)}</option>`)}</select>`:c}
          </div>`:s`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`}var Je=["auto","idle","heating","cooling"];function dr(n,e){const t=e.plant;const r=`Mode ${N(n.localize,"select.requested_mode",t.requested_mode)}`;if(t.requested_mode==="auto"||t.requested_mode===t.active_mode)return r;return`${r} \xB7 now ${N(n.localize,"sensor.operating_mode",t.active_mode)}`}function an(n,e,t){const r=e.plant;const o=r.execution_boundary;const a=e.controls.requested_mode;const i=Je.includes(r.requested_mode)?Je:[...Je,r.requested_mode];const u=xt(e);const l=vt(r.health);const d=p=>n.call(ft(e,p.target.value));return s`<header class="header" part="header">
      <div class="plant-heading">
        <span class="plant-mark" part="mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow" part="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title" part="title">${a?s`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>n.moreInfo(a)}>${r.name}</button>`:r.name}</h2>
          <div class="status-line" part="status">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${N(n.localize,"sensor.controller_status",r.status)}</span>
            ${l===null?c:s`<span class="health" data-health=${r.health}><span class="visually-hidden">Health: </span>${l}</span>`}
            <span class="meta mode-detail">${dr(n,e)}</span>
          </div>
          ${u===null?c:s`<p class="meta source-line" dir="auto"><strong>Source</strong> ${u}</p>`}
          <p class="meta" dir="auto">${r.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls" part="controls">
        <span class="badge ${_t(o)}" part="badge"><span class="visually-hidden">Execution boundary: </span>${Ce(o)}</span>
        <label class="mode-control" part="control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${r.requested_mode} ?disabled=${!a} @change=${d}>
          ${i.map(p=>s`<option value=${p}>${N(n.localize,"select.requested_mode",p)}</option>`)}
        </select></label>
        ${t}
      </div>
    </header>`}function sn(n){return s`<div class="boundary" part="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${n.plant.execution_boundary.message||`${Ce(n.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`}function ln(n,e){const t=we(e);if(!t.length)return c;return s`<section part="section" aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${g(t.length,n.locale,0)}</span></div>${t.slice(0,3).map(r=>{const o=r.severity==="error"||r.severity==="critical";return s`<p class="alert ${o?"error":""}" part="notice" data-severity=${r.severity} dir="auto"><strong>${wt(r)}</strong><span> · ${r.message}</span></p>`})}</section>`}function cn(n,e){return s`<section part="section" aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-zones">Zones</h3></div><span class="meta" dir="auto">${g(e.zones.length,n.locale,0)} visible</span></div><div class="zone-grid">${e.zones.length?e.zones.map(t=>de(n,t,{headingLevel:4,alerts:X(e,t.id)})):s`<p class="muted empty-state" dir="auto">No Zones are visible for this Plant.</p>`}</div></section>`}function dn(n){if(!n.delivery_paths.length)return c;return s`<section part="section" aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Zone → Loop → Valve → Pump → Source</span></div><div class="path-list">${n.delivery_paths.map(e=>{const t=n.zones.find(r=>r.id===e.zone_id);return s`<article class="path" part="path" data-status=${e.status} data-flowing=${String($e(e.status))} data-demand-kind=${Y(t)}>
    <div class="path-head"><div class="path-heading"><strong>${t?.name??e.zone_id}</strong></div><div class="status-line"><span class="state ${e.status}" part="badge">${f(e.status)}</span>${e.coupled?s`<span class="meta">shares equipment</span>`:c}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${e.nodes.map((r,o)=>s`<li class="path-step">${o?s`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" part="node" data-kind=${r.kind} data-state=${r.state} data-flowing=${String($e(r.state))}><span class="node-kind">${Ee(r.kind)}</span><span class="node-name">${r.name}</span><span class="node-state">${f(r.state)}</span></span></li>`)}</ol>
    ${e.problem?s`<p class="meta path-problem" dir="auto">${e.problem}</p>`:c}
  </article>`})}</div></section>`}function un(n){if(!n.actuators.length)return c;return s`<section part="section" aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${n.actuators.map(e=>s`<article class="actuator" part="equipment" data-state=${e.state}><div class="row"><strong>${e.name}</strong><span class="state actuator-state ${e.state}" part="badge">${f(e.state)}</span></div><p class="meta" dir="auto">${f(e.kind)} · ${e.reason??"No additional explanation."}</p>${e.active_consumers.length?s`<ul class="consumer-list" aria-label="Loops using this equipment">${e.active_consumers.map(t=>s`<li class="consumer-chip" part="chip" title=${t.id}><strong>${t.name}</strong></li>`)}</ul>`:s`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}function hn(n){return s`<section part="section"><details part="disclosure"><summary>Controller explanations</summary>${n.explanations.map(e=>s`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${e.name??Ee(e.scope)}</strong> · ${e.message}</p></div>`)}</details></section>`}function pn(n,e){const t=Object.values(e.execution.operations).flat();if(!t.length)return c;return s`<section part="section"><details part="disclosure" open><summary>Latest operation outcomes (${g(t.length,n.locale,0)})</summary>${t.map(r=>{const o=String(r.result??"unknown");return s`<div class="operation" data-result=${o}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${yt(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}function mn(n){return`Retrying in ${Math.round(n/1e3)} s.`}function v(n,e,t,r,o){return s`<ha-card part="card" class="state-card" data-visual=${r==="alert"?"attention":"idle"}>
    <div class="plant-heading"><span class="plant-mark" part="mark" aria-hidden="true"></span><div><p class="eyebrow" part="eyebrow">${n}</p><h2 part="title">${e}</h2></div></div>
    <p class=${r==="alert"?"notice error":"notice"} part="notice" role=${r} dir="auto">${t}</p>
    ${o?s`<p class="meta" dir="auto">${o}</p>`:c}
  </ha-card>`}function ur(n){return s`<ha-card part="card" class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${n?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
  </ha-card>`}function ue(n){return n.snapshotError?null:n.snapshot}function he(n,e){if(e.snapshotError){return v(n,"Card update needed",e.snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const t=e.status;switch(t.kind){case"not_found":return v(n,"Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return v(n,"No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return v(n,"Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return v(n,"Connection needs attention",t.message,"alert",mn(t.delayMs));default:return ur(t.kind==="reconnecting")}}function pe(n){if(n.kind==="reconnecting"){return s`<p class="notice" part="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(n.kind==="retrying"){return s`<p class="notice" part="notice" role="status" dir="auto">${n.message} ${mn(n.delayMs)} The values below may be out of date.</p>`}return c}function me(n,e){if(!n)return c;return s`<div class="action-error" part="notice" role="alert"><span dir="auto">${n}</span><button type="button" part="control" @click=${e}>Dismiss</button></div>`}var hr=1200;var Qe="Hydronicus Plant";var pr=["zones","paths","equipment"];function mr(n,e){switch(n){case"header":return 4;case"alerts":{const t=Math.min(e.alerts.length,3);return t?1+t:0}case"zones":return 1+(e.zones.length?e.zones.reduce((t,r)=>t+Q(r),0):5);case"paths":return e.delivery_paths.length?1+e.delivery_paths.length*3:0;case"equipment":return e.actuators.length?1+e.actuators.length*2:0;case"explanations":return 1;case"operations":{const t=Object.values(e.execution.operations).flat().length;return t?1+t:0}}}var fe=class extends q{static properties={_config:{state:true},_holdingShutdown:{state:true}};_holdTimer=null;constructor(){super();this._config=void 0;this._holdingShutdown=false}static async getConfigForm(){return Mt()}static async getStubConfig(e){return Rt(e)}setConfig(e){const t=Me(e);if(t.plant!==this._config?.plant)this.resetPlant();this._config=t}get plantId(){return this._config?.plant}getCardSize(){const e=this._plant.snapshot;const t=oe(this._config);if(!e)return t.includes("header")?4:2;return Math.max(1,t.reduce((r,o)=>r+mr(o,e),0))}getGridOptions(){const e=oe(this._config).some(t=>pr.includes(t));return e?{columns:12,min_columns:6}:{columns:6,min_columns:4}}disconnectedCallback(){this._clearHold();super.disconnectedCallback()}plantStateChanged(e){if(!e.snapshot)this._clearHold()}render(){const e=this._config;if(!e||!e.plant){return v(Qe,Qe,"Select a Hydronicus Plant in the card editor.","status")}const t=this._plant;const r=ue(t);if(!r)return he(Qe,t);const o=this.renderContext;const a=oe(e);const i=s`${pe(t.status)}${me(this._actionError,this.dismissActionError)}`;return s`<ha-card part="card" class=${e.density??"comfortable"} data-visual=${ct(r)}>
      ${a.includes("header")?c:i}
      ${a.map(u=>this._renderSection(u,o,r,i))}
    </ha-card>`}_renderSection(e,t,r,o){switch(e){case"header":return s`${an(t,r,this._renderShutdown(r))}
          ${o}
          ${sn(r)}`;case"alerts":return ln(t,r);case"zones":return cn(t,r);case"paths":return dn(r);case"equipment":return un(r);case"explanations":return hn(r);case"operations":return pn(t,r)}}_renderShutdown(e){const t=!e.controls.safe_shutdown;const r=e.plant.execution_boundary.dry_run;return s`<button type="button" part="control" class=${`shutdown${r?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${t} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?s`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_startHold(){if(!this._plant.snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;const e=this._plant.snapshot;if(e)this.call(gt(e))},hr)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=e=>{if(e.button!==void 0&&e.button>0)return;this._startHold()};_keyHoldStart=e=>{if(e.key!=="Enter"&&e.key!==" ")return;e.preventDefault();if(!e.repeat)this._startHold()};_keyHoldEnd=e=>{if(e.key==="Enter"||e.key===" ")this._clearHold()};_preventContextMenu=e=>{e.preventDefault()}};var U="Hydronicus Zone";var ge=class extends q{static properties={_config:{state:true}};constructor(){super();this._config=void 0}static getConfigElement(){return document.createElement(re)}static async getStubConfig(e){return Ht(e)}setConfig(e){const t=ae(e);if(t.plant!==this._config?.plant)this.resetPlant();else if(t.zone!==this._config?.zone)this._actionError=null;this._config=t}get plantId(){return this._config?.zone?this._config.plant:void 0}getCardSize(){const e=this._plant.snapshot?.zones.find(t=>t.id===this._config?.zone);return e?Q(e):5}getGridOptions(){return{columns:6,min_columns:4}}render(){const e=this._config;if(!e||!e.plant){return v(U,U,"Select a Hydronicus Plant and a Zone in the card editor.","status")}if(!e.zone){return v(U,U,"Select a Zone in the card editor.","status")}const t=this._plant;const r=ue(t);if(!r)return he(U,t);const o=r.zones.find(i=>i.id===e.zone);if(!o){return v(U,"Zone not found","This Zone is not in the Plant, or you do not have access to it. Choose another Zone in the card editor.","alert")}const a=X(r,o.id);return s`<ha-card part="card" class="zone-card ${e.density??"comfortable"}" data-visual=${ut(o,a)}>
      ${pe(t.status)}
      ${me(this._actionError,this.dismissActionError)}
      ${de(this.renderContext,o,{headingLevel:2,alerts:a})}
    </ha-card>`}};var ye=class extends x{static properties={hass:{attribute:false},_config:{state:true},_plants:{state:true},_zones:{state:true}};_release;_followed;_directoryConnection;constructor(){super();this.hass=void 0;this._config=void 0;this._plants=_.known;this._zones=[]}setConfig(e){ae(e);this._config=e}connectedCallback(){super.connectedCallback();this.requestUpdate()}disconnectedCallback(){this._unfollow();this._directoryConnection=void 0;super.disconnectedCallback()}updated(e){super.updated(e);if(!this.isConnected)return;const t=this.hass?.connection;if(t&&t!==this._directoryConnection){this._directoryConnection=t;void _.load(t).then(r=>{this._plants=r})}this._follow(t,this._config?.plant||void 0)}_follow(e,t){const r=this._followed;if(r?.connection===e&&r?.plantId===t)return;this._unfollow();if(!e||!t)return;this._followed={connection:e,plantId:t};this._release=H.subscribe(e,t,o=>{if(o.snapshot)this._zones=o.snapshot.zones.map(a=>({id:a.id,name:a.name}))})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._zones=[]}render(){return s`<ha-form
      .hass=${this.hass}
      .data=${this._config??{}}
      .schema=${Ot(this._plants,this._zones)}
      .computeLabel=${Oe}
      .computeHelper=${qe}
      @value-changed=${this._valueChanged}
    ></ha-form>`}_valueChanged(e){e.stopPropagation();const t={...e.detail.value};if(t.plant!==this._config?.plant)t.zone="";this._config=t;this.dispatchEvent(new CustomEvent("config-changed",{bubbles:true,composed:true,detail:{config:t}}))}};var fr=[[te,fe],[ne,ge],[re,ye]];function fn(n){for(const[e,t]of fr){if(!n.get(e))n.define(e,t)}}var gn=window.customElements;fn(gn);void gn.whenDefined("home-assistant").then(()=>{fn(window.customElements)});var gr=[{type:te,name:"Hydronicus Plant",description:"Topology-driven Hydronicus Plant status and controls.",preview:false},{type:ne,name:"Hydronicus Zone",description:"One Zone of a Hydronicus Plant, with its thermostat and controls.",preview:true}];window.customCards=window.customCards??[];for(const n of gr){if(window.customCards.some(e=>e.type===n.type))continue;window.customCards.push({...n,version:"0.1.0",documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
