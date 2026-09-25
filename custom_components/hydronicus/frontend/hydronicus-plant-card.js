var C="\xB0C";var cn=5;var dn=35;function gt(n){return n?.temperature==="\xB0F"?"\xB0F":C}function K(n,t){return t==="\xB0F"?n*9/5+32:n}function un(n,t){return t==="\xB0F"?n*9/5:n}function yt(n){return n==="\xB0F"?1:.5}function Qt(n,t,e){const r=yt(e);const o=K(n,e);const i=o/r;const s=(t>0?Math.floor(i+1e-9)+1:Math.ceil(i-1e-9)-1)*r;const u=K(cn,e);const l=K(dn,e);return Number(Math.min(l,Math.max(u,s)).toFixed(1))}function hn(n){switch(n?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return n?.language}}var Jt=new Map;function y(n,t,e=1){const r=hn(t);const o=t?.number_format!=="none";const i=`${JSON.stringify(r)}|${e}|${o}`;let s=Jt.get(i);if(!s){try{s=new Intl.NumberFormat(r,{minimumFractionDigits:e,maximumFractionDigits:e,useGrouping:o})}catch{s=new Intl.NumberFormat(void 0,{minimumFractionDigits:e,maximumFractionDigits:e})}Jt.set(i,s)}return s.format(n)}function bt(n,t,e){return y(K(n,t),e)}function te(n,t,e){return y(un(n,t),e)}var pn=2;var mn=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function ee(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const t=n;if(t.schema_version!==pn){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(t.schema_version)}.`)}if(!t.plant||!Array.isArray(t.zones)||!Array.isArray(t.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return t}function ne(n){return[...n.alerts].sort((t,e)=>t.priority-e.priority||t.code.localeCompare(e.code)||t.scope.localeCompare(e.scope))}function re(n){const t=n.plant.health.toLowerCase();const e=n.alerts.some(o=>o.severity==="critical"||o.severity==="error");if(n.safe_shutdown.active||e||["blocked","critical","error","failed","unhealthy"].includes(t)){return"attention"}const r=`${n.plant.active_mode} ${n.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function oe(n){if(n.blocked)return"attention";if(n.cooling.demand)return"cooling";if(n.demand)return"heating";return"idle"}function vt(n){return mn.has(n.toLowerCase())}function G(n){if(!n)return"none";return n.cooling.demand?"cooling":n.demand?"heating":"none"}function ie(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:n.thermostat.control_entity_id,temperature:t}}}function se(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:n.thermostat.control_entity_id,preset_mode:t}}}function ae(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;if(!xt(n).includes(t))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:n.thermostat.control_entity_id,hvac_mode:t}}}function le(n,t){if(!n.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:n.controls.requested_mode,option:t}}}function ce(n){if(!n.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:n.controls.safe_shutdown}}}function de(n){const t=String(n.action??"operation").replaceAll("_"," ");const e=String(n.actuator_name??"actuator");const r=String(n.result??"");if(r==="proposed")return`Would ${t} ${e}`;if(r==="executed")return`Executed ${e} ${t}`;if(r==="suppressed")return`Suppressed ${e} ${t}`;return`${r||"Operation"}: ${e} ${t}`}function fn(n){return n.replaceAll("_"," ")}function N(n,t,e){const[r,o]=t.split(".");return n?.(`component.hydronicus.entity.${r}.${o}.state.${e}`)||f(e)}function f(n){const t=fn(n);return t.charAt(0).toUpperCase()+t.slice(1)}var gn={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function _t(n,t){return n?.(`component.climate.entity_component._.state.${t}`)||gn[t]||f(t)}function xt(n){if(n.thermostat.kind!=="hydronicus")return[];return[...new Set(n.thermostat.hvac_modes??[])]}function wt(n){if(n.dry_run||n.mode==="dry_run")return"Dry run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"Live";return f(n.mode)}function ue(n){if(n.dry_run||n.mode==="dry_run")return"dry-run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"live";return n.mode.replaceAll("_","-")}function he(n){const{active_name:t,recommended_name:e}=n.plant.source;if(!n.sources.length&&!t&&!e)return null;const r=[t??"None active"];if(e&&e!==t)r.push(`recommended ${e}`);return r.join(" \xB7 ")}var yn={zone:"Room",circuit:"Loop"};var bn={plant_initializing:"Starting",plant_unavailable:"Plant unavailable",binding_unavailable:"Entity unavailable",zone_sensor_blocked:"Sensor blocked",zone_mode_blocked:"Room blocked",cooling_blocked:"Cooling blocked",actuator_mismatch:"Equipment mismatch",actuator_blocked:"Equipment blocked",mode_changeover:"Mode changeover"};function pe(n){const t=bn[n.code]??f(n.code);return n.scope!=="plant"&&n.name?`${n.name} \xB7 ${t}`:t}function $t(n){return yn[n]??f(n)}function me(n){return[...new Set(n.thermostat.preset_modes)].filter(t=>t!=="none")}function fe(n,t,e=C){if(n.thermostat.target_temperature===null)return null;return Qt(n.thermostat.target_temperature,t,e)}var vn="hydronicus/subscribe_plant";var _n=1e3;var xn=6e4;var wn={setTimeout:(n,t)=>globalThis.setTimeout(n,t),clearTimeout:n=>globalThis.clearTimeout(n)};var ge={plant_not_found:"not_found",unauthorized:"unauthorized"};function ye(n){return n!==void 0&&Object.hasOwn(ge,n)?ge[n]:void 0}function $n(n){return typeof n==="object"&&n!==null&&"code"in n?String(n.code):void 0}function D(n,t){if(n instanceof Error)return n.message;if(typeof n==="object"&&n!==null&&"message"in n&&n.message){return String(n.message)}return t}function kt(n){if(!n)return;try{void Promise.resolve(n()).catch(()=>void 0)}catch{}}var X=class{constructor(t,e=wn){this.host=t;this.scheduler=e}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(t,e){if(t===this.connection&&e===this.plantId)return;this.disconnect();if(!t||!e)return;this.connection=t;this.plantId=e;t.addEventListener?.("disconnected",this.handleDisconnected);t.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;kt(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const t=this.connection;const e=this.plantId;if(!t||!e)return;this.cancelRetry();const r=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}t.subscribeMessage(o=>this.handleEvent(r,o),{type:vn,plant_id:e},{resubscribe:false}).then(o=>{if(r!==this.generation){kt(o);return}this.unsubscribe=o}).catch(o=>{if(r!==this.generation)return;this.handleError(o)})}handleEvent(t,e){if(t!==this.generation)return;if(e.snapshot!==void 0&&e.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(e.snapshot);return}if(e.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const r=ye(e.status);if(r)this.stop({kind:r})}handleError(t){const e=ye($n(t));if(e){this.stop({kind:e});return}const r=Math.min(_n*2**this.attempt,xn);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:r,message:D(t,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},r)}stop(t){this.cancelRetry();this.generation+=1;kt(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(t)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(t){this.current=t;this.host.onStatus(t)}};var H={status:{kind:"idle"},snapshot:null,snapshotError:null};var kn=new Set(["idle","unavailable","not_found","unauthorized"]);var St=class{listeners=new Set;current=H;stream;constructor(t){this.stream=new X({onStatus:e=>this.statusChanged(e),onSnapshot:e=>this.snapshotReceived(e)},t)}get state(){return this.current}open(t,e){this.stream.connect(t,e)}close(){this.stream.disconnect()}statusChanged(t){const e=kn.has(t.kind)?null:this.current.snapshot;this.publish({...this.current,status:t,snapshot:e})}snapshotReceived(t){try{this.publish({...this.current,snapshot:ee(t),snapshotError:null})}catch(e){this.publish({...this.current,snapshot:null,snapshotError:D(e,"Unsupported Hydronicus snapshot.")})}}publish(t){this.current=t;for(const e of[...this.listeners])e(t)}};var Ct=class{constructor(t){this.scheduler=t}scheduler;feeds=new WeakMap;subscribe(t,e,r){let o=this.feeds.get(t);if(!o){o=new Map;this.feeds.set(t,o)}let i=o.get(e);const s=!i;if(!i){i=new St(this.scheduler);o.set(e,i)}i.listeners.add(r);if(s)i.open(t,e);else r(i.state);const u=o;const l=i;let d=false;return()=>{if(d)return;d=true;l.listeners.delete(r);if(l.listeners.size)return;queueMicrotask(()=>{if(l.listeners.size||u.get(e)!==l)return;u.delete(e);l.close()})}}snapshot(t,e,r=2e3){return new Promise(o=>{let i=false;const s=d=>{if(i)return;i=true;clearTimeout(u);queueMicrotask(()=>l());o(d)};const u=setTimeout(()=>s(null),r);const l=this.subscribe(t,e,d=>{if(d.snapshot)s(d.snapshot);else if(["not_found","unauthorized"].includes(d.status.kind)||d.snapshotError)s(null)})})}};var z=new Ct;var Y="hydronicus-plant-card";var be=`custom:${Y}`;var J="hydronicus-room-card";var ve=`custom:${J}`;var Q="hydronicus-room-card-editor";var Sn="hydronicus/list_plants";var Cn=["comfortable","compact"];var _e=[{value:"header",label:"Header and execution boundary"},{value:"alerts",label:"Alerts"},{value:"rooms",label:"Rooms"},{value:"paths",label:"Hydraulic flow"},{value:"equipment",label:"Equipment"},{value:"explanations",label:"Controller explanations"},{value:"operations",label:"Operation outcomes"}];var At=_e.map(n=>n.value);function xe(n,t,e){if(!n||typeof n!=="object"){throw new Error(`${t} requires a configuration.`)}const r=n;if(r.type!==e){throw new Error(`${t} type must be ${e}.`)}if(typeof r.plant!=="string"){throw new Error(`${t} requires one Plant UUID in \`plant\`.`)}return r}function we(n,t){const e=n??"comfortable";if(!Cn.includes(e)){throw new Error(`${t} density must be comfortable or compact.`)}return e}function An(n){if(n===void 0||n===null)return void 0;if(!Array.isArray(n)){throw new Error("Hydronicus Plant card `sections` must be a list of section names.")}const t=new Set;for(const e of n){if(typeof e!=="string"||!At.includes(e)){throw new Error(`Hydronicus Plant card section ${JSON.stringify(e)} is unknown. Use ${At.join(", ")}.`)}if(t.has(e)){throw new Error(`Hydronicus Plant card section ${e} is listed twice.`)}t.add(e)}return n.length?n:void 0}function Rt(n){const t="Hydronicus Plant card";const e=xe(n,t,be);const r=we(e.density,t);const o=An(e.sections);return{type:be,plant:e.plant.trim(),density:r,...o?{sections:o}:{}}}function tt(n){return n?.sections??At}function et(n){const t="Hydronicus Room card";const e=xe(n,t,ve);const r=e.room??"";if(typeof r!=="string"){throw new Error(`${t} requires one Room id in \`room\`.`)}const o=we(e.density,t);return{type:ve,plant:e.plant.trim(),room:r.trim(),density:o}}var Et=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(t){if(this.connection===t&&this.pending)return this.pending;this.connection=t;this.pending=t.sendMessagePromise({type:Sn}).then(e=>{this.plants=Array.isArray(e.plants)?e.plants:[];return this.plants}).catch(()=>{if(this.connection===t)this.pending=null;return this.plants});return this.pending}async settled(t=2e3){if(!this.pending)return this.plants;let e;const r=new Promise(o=>{e=setTimeout(()=>o(this.plants),t)});try{return await Promise.race([this.pending,r])}finally{clearTimeout(e)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var v=new Et;async function $e(n){const t=n?.connection?await v.load(n.connection):v.known;return{plant:t[0]?.id??"",density:"comfortable"}}async function ke(n){const t=n?.connection;const e=t?await v.load(t):v.known;const r=e[0]?.id??"";const o=t&&r?await z.snapshot(t,r):null;return{plant:r,room:o?.zones[0]?.id??"",density:"comfortable"}}var En={plant:"Hydronicus Plant",room:"Room",density:"Density",sections:"Sections"};var Pn={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",room:"The Room this card shows. Only Rooms you can read are listed; one that is not listed shows its id.",density:"Compact uses less spacing for dense dashboards.",sections:"The parts of the Plant to show, in this order. Leave empty to show every section."};var Tt=n=>En[n.name];var Ht=n=>Pn[n.name];function Pt(n){if(n.length===0)return{text:{}};return{select:{mode:"dropdown",options:n.map(t=>({value:t.id,label:t.name}))}}}var Se={name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}};async function Ce(){const n=await v.settled();return{schema:[{name:"plant",required:true,selector:Pt(n)},Se,{name:"sections",selector:{select:{multiple:true,reorder:true,mode:"dropdown",options:_e.map(t=>({...t}))}}}],computeLabel:Tt,computeHelper:Ht,assertConfig:t=>{Rt(t)}}}function Ae(n,t){return[{name:"plant",required:true,selector:Pt(n)},{name:"room",required:true,selector:Pt(t)},Se]}var nt=globalThis;var rt=nt.ShadowRoot&&(void 0===nt.ShadyCSS||nt.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var zt=Symbol();var Ee=new WeakMap;var I=class{constructor(t,e,r){if(this._$cssResult$=true,r!==zt)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(rt&&void 0===t){const r=void 0!==e&&1===e.length;r&&(t=Ee.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),r&&Ee.set(e,t))}return t}toString(){return this.cssText}};var Pe=n=>new I("string"==typeof n?n:n+"",void 0,zt);var Lt=(n,...t)=>{const e=1===n.length?n[0]:t.reduce((r,o,i)=>r+(s=>{if(true===s._$cssResult$)return s.cssText;if("number"==typeof s)return s;throw Error("Value passed to 'css' function must be a 'css' function result: "+s+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[i+1],n[0]);return new I(e,n,zt)};var Re=(n,t)=>{if(rt)n.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const e of t){const r=document.createElement("style"),o=nt.litNonce;void 0!==o&&r.setAttribute("nonce",o),r.textContent=e.cssText,n.appendChild(r)}};var Mt=rt?n=>n:n=>n instanceof CSSStyleSheet?(t=>{let e="";for(const r of t.cssRules)e+=r.cssText;return Pe(e)})(n):n;var{is:Rn,defineProperty:Tn,getOwnPropertyDescriptor:Hn,getOwnPropertyNames:zn,getOwnPropertySymbols:Ln,getPrototypeOf:Mn}=Object;var ot=globalThis;var Te=ot.trustedTypes;var On=Te?Te.emptyScript:"";var qn=ot.reactiveElementPolyfillSupport;var F=(n,t)=>n;var Ot={toAttribute(n,t){switch(t){case Boolean:n=n?On:null;break;case Object:case Array:n=null==n?n:JSON.stringify(n)}return n},fromAttribute(n,t){let e=n;switch(t){case Boolean:e=null!==n;break;case Number:e=null===n?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch(r){e=null}}return e}};var ze=(n,t)=>!Rn(n,t);var He={attribute:true,type:String,converter:Ot,reflect:false,useDefault:false,hasChanged:ze};Symbol.metadata??=Symbol("metadata"),ot.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=He){if(e.state&&(e.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=true),this.elementProperties.set(t,e),!e.noAccessor){const r=Symbol(),o=this.getPropertyDescriptor(t,r,e);void 0!==o&&Tn(this.prototype,t,o)}}static getPropertyDescriptor(t,e,r){const{get:o,set:i}=Hn(this.prototype,t)??{get(){return this[e]},set(s){this[e]=s}};return{get:o,set(s){const u=o?.call(this);i?.call(this,s),this.requestUpdate(t,u,r)},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??He}static _$Ei(){if(this.hasOwnProperty(F("elementProperties")))return;const t=Mn(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(F("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(F("properties"))){const e=this.properties,r=[...zn(e),...Ln(e)];for(const o of r)this.createProperty(o,e[o])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[r,o]of e)this.elementProperties.set(r,o)}this._$Eh=new Map;for(const[e,r]of this.elementProperties){const o=this._$Eu(e,r);void 0!==o&&this._$Eh.set(o,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const r=new Set(t.flat(1/0).reverse());for(const o of r)e.unshift(Mt(o))}else void 0!==t&&e.push(Mt(t));return e}static _$Eu(t,e){const r=e.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const r of e.keys())this.hasOwnProperty(r)&&(t.set(r,this[r]),delete this[r]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Re(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,r){this._$AK(t,r)}_$ET(t,e){const r=this.constructor.elementProperties.get(t),o=this.constructor._$Eu(t,r);if(void 0!==o&&true===r.reflect){const i=(void 0!==r.converter?.toAttribute?r.converter:Ot).toAttribute(e,r.type);this._$Em=t,null==i?this.removeAttribute(o):this.setAttribute(o,i),this._$Em=null}}_$AK(t,e){const r=this.constructor,o=r._$Eh.get(t);if(void 0!==o&&this._$Em!==o){const i=r.getPropertyOptions(o),s="function"==typeof i.converter?{fromAttribute:i.converter}:void 0!==i.converter?.fromAttribute?i.converter:Ot;this._$Em=o;const u=s.fromAttribute(e,i.type);this[o]=u??this._$Ej?.get(o)??u,this._$Em=null}}requestUpdate(t,e,r,o=false,i){if(void 0!==t){const s=this.constructor;if(false===o&&(i=this[t]),r??=s.getPropertyOptions(t),!((r.hasChanged??ze)(i,e)||r.useDefault&&r.reflect&&i===this._$Ej?.get(t)&&!this.hasAttribute(s._$Eu(t,r))))return;this.C(t,e,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:r,reflect:o,wrapped:i},s){r&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,s??e??this[t]),true!==i||void 0!==s)||(this._$AL.has(t)||(this.hasUpdated||r||(e=void 0),this._$AL.set(t,e)),true===o&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(e){Promise.reject(e)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[o,i]of this._$Ep)this[o]=i;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[o,i]of r){const{wrapped:s}=i,u=this[o];true!==s||this._$AL.has(o)||void 0===u||this.C(o,void 0,i,u)}}let t=false;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(e)):this._$EM()}catch(r){throw t=false,this._$EM(),r}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return true}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[F("elementProperties")]=new Map,w[F("finalized")]=new Map,qn?.({ReactiveElement:w}),(ot.reactiveElementVersions??=[]).push("2.1.2");var Vt=globalThis;var Le=n=>n;var it=Vt.trustedTypes;var Me=it?it.createPolicy("lit-html",{createHTML:n=>n}):void 0;var Ie="$lit$";var k=`lit$${Math.random().toFixed(9).slice(2)}$`;var Fe="?"+k;var Un=`<${Fe}>`;var P=document;var j=()=>P.createComment("");var B=n=>null===n||"object"!=typeof n&&"function"!=typeof n;var jt=Array.isArray;var Nn=n=>jt(n)||"function"==typeof n?.[Symbol.iterator];var qt="[ 	\n\f\r]";var V=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Oe=/-->/g;var qe=/>/g;var A=RegExp(`>|${qt}(?:([^\\s"'>=/]+)(${qt}*=${qt}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Ue=/'/g;var Ne=/"/g;var Ve=/^(?:script|style|textarea|title)$/i;var Bt=n=>(t,...e)=>({_$litType$:n,strings:t,values:e});var a=Bt(1);var gr=Bt(2);var yr=Bt(3);var R=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var De=new WeakMap;var E=P.createTreeWalker(P,129);function je(n,t){if(!jt(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Me?Me.createHTML(t):t}var Dn=(n,t)=>{const e=n.length-1,r=[];let o,i=2===t?"<svg>":3===t?"<math>":"",s=V;for(let u=0;u<e;u++){const l=n[u];let d,p,h=-1,m=0;for(;m<l.length&&(s.lastIndex=m,p=s.exec(l),null!==p);)m=s.lastIndex,s===V?"!--"===p[1]?s=Oe:void 0!==p[1]?s=qe:void 0!==p[2]?(Ve.test(p[2])&&(o=RegExp("</"+p[2],"g")),s=A):void 0!==p[3]&&(s=A):s===A?">"===p[0]?(s=o??V,h=-1):void 0===p[1]?h=-2:(h=s.lastIndex-p[2].length,d=p[1],s=void 0===p[3]?A:'"'===p[3]?Ne:Ue):s===Ne||s===Ue?s=A:s===Oe||s===qe?s=V:(s=A,o=void 0);const g=s===A&&n[u+1].startsWith("/>")?" ":"";i+=s===V?l+Un:h>=0?(r.push(d),l.slice(0,h)+Ie+l.slice(h)+k+g):l+k+(-2===h?u:g)}return[je(n,i+(n[e]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),r]};var W=class n{constructor({strings:t,_$litType$:e},r){let o;this.parts=[];let i=0,s=0;const u=t.length-1,l=this.parts,[d,p]=Dn(t,e);if(this.el=n.createElement(d,r),E.currentNode=this.el.content,2===e||3===e){const h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;null!==(o=E.nextNode())&&l.length<u;){if(1===o.nodeType){if(o.hasAttributes())for(const h of o.getAttributeNames())if(h.endsWith(Ie)){const m=p[s++],g=o.getAttribute(h).split(k),S=/([.?@])?(.*)/.exec(m);l.push({type:1,index:i,name:S[2],strings:g,ctor:"."===S[1]?Nt:"?"===S[1]?Dt:"@"===S[1]?It:M}),o.removeAttribute(h)}else h.startsWith(k)&&(l.push({type:6,index:i}),o.removeAttribute(h));if(Ve.test(o.tagName)){const h=o.textContent.split(k),m=h.length-1;if(m>0){o.textContent=it?it.emptyScript:"";for(let g=0;g<m;g++)o.append(h[g],j()),E.nextNode(),l.push({type:2,index:++i});o.append(h[m],j())}}}else if(8===o.nodeType)if(o.data===Fe)l.push({type:2,index:i});else{let h=-1;for(;-1!==(h=o.data.indexOf(k,h+1));)l.push({type:7,index:i}),h+=k.length-1}i++}}static createElement(t,e){const r=P.createElement("template");return r.innerHTML=t,r}};function L(n,t,e=n,r){if(t===R)return t;let o=void 0!==r?e._$Co?.[r]:e._$Cl;const i=B(t)?void 0:t._$litDirective$;return o?.constructor!==i&&(o?._$AO?.(false),void 0===i?o=void 0:(o=new i(n),o._$AT(n,e,r)),void 0!==r?(e._$Co??=[])[r]=o:e._$Cl=o),void 0!==o&&(t=L(n,o._$AS(n,t.values),o,r)),t}var Ut=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:r}=this._$AD,o=(t?.creationScope??P).importNode(e,true);E.currentNode=o;let i=E.nextNode(),s=0,u=0,l=r[0];for(;void 0!==l;){if(s===l.index){let d;2===l.type?d=new Z(i,i.nextSibling,this,t):1===l.type?d=new l.ctor(i,l.name,l.strings,this,t):6===l.type&&(d=new Ft(i,this,t)),this._$AV.push(d),l=r[++u]}s!==l?.index&&(i=E.nextNode(),s++)}return E.currentNode=P,o}p(t){let e=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(t,r,e),e+=r.strings.length-2):r._$AI(t[e])),e++}};var Z=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,r,o){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??true}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=L(this,t,e),B(t)?t===c||null==t||""===t?(this._$AH!==c&&this._$AR(),this._$AH=c):t!==this._$AH&&t!==R&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):Nn(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==c&&B(this._$AH)?this._$AA.nextSibling.data=t:this.T(P.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:r}=t,o="number"==typeof r?this._$AC(t):(void 0===r.el&&(r.el=W.createElement(je(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(e);else{const i=new Ut(o,this),s=i.u(this.options);i.p(e),this.T(s),this._$AH=i}}_$AC(t){let e=De.get(t.strings);return void 0===e&&De.set(t.strings,e=new W(t)),e}k(t){jt(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let r,o=0;for(const i of t)o===e.length?e.push(r=new n(this.O(j()),this.O(j()),this,this.options)):r=e[o],r._$AI(i),o++;o<e.length&&(this._$AR(r&&r._$AB.nextSibling,o),e.length=o)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(false,true,e);t!==this._$AB;){const r=Le(t).nextSibling;Le(t).remove(),t=r}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}};var M=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,r,o,i){this.type=1,this._$AH=c,this._$AN=void 0,this.element=t,this.name=e,this._$AM=o,this.options=i,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=c}_$AI(t,e=this,r,o){const i=this.strings;let s=false;if(void 0===i)t=L(this,t,e,0),s=!B(t)||t!==this._$AH&&t!==R,s&&(this._$AH=t);else{const u=t;let l,d;for(t=i[0],l=0;l<i.length-1;l++)d=L(this,u[r+l],e,l),d===R&&(d=this._$AH[l]),s||=!B(d)||d!==this._$AH[l],d===c?t=c:t!==c&&(t+=(d??"")+i[l+1]),this._$AH[l]=d}s&&!o&&this.j(t)}j(t){t===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}};var Nt=class extends M{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===c?void 0:t}};var Dt=class extends M{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==c)}};var It=class extends M{constructor(t,e,r,o,i){super(t,e,r,o,i),this.type=5}_$AI(t,e=this){if((t=L(this,t,e,0)??c)===R)return;const r=this._$AH,o=t===c&&r!==c||t.capture!==r.capture||t.once!==r.once||t.passive!==r.passive,i=t!==c&&(r===c||o);o&&this.element.removeEventListener(this.name,this,r),i&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}};var Ft=class{constructor(t,e,r){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(t){L(this,t)}};var In=Vt.litHtmlPolyfillSupport;In?.(W,Z),(Vt.litHtmlVersions??=[]).push("3.3.3");var Be=(n,t,e)=>{const r=e?.renderBefore??t;let o=r._$litPart$;if(void 0===o){const i=e?.renderBefore??null;r._$litPart$=o=new Z(t.insertBefore(j(),i),i,void 0,e??{})}return o._$AI(n),o};var Wt=globalThis;var _=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Be(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return R}};_._$litElement$=true,_["finalized"]=true,Wt.litElementHydrateSupport?.({LitElement:_});var Fn=Wt.litElementPolyfillSupport;Fn?.({LitElement:_});(Wt.litElementVersions??=[]).push("4.2.2");var T=class extends Event{constructor(t,e,r,o){super("context-request",{bubbles:true,composed:true}),this.context=t,this.contextTarget=e,this.callback=r,this.subscribe=o??false}};function O(n){return n}var $=class{constructor(t,e,r,o){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(i,s)=>{this.unsubscribe&&(this.unsubscribe!==s&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=i,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(i,s)),this.unsubscribe=s},this.host=t,void 0!==e.context){const i=e;this.context=i.context,this.callback=i.callback,this.subscribe=i.subscribe??false}else this.context=e,this.callback=r,this.subscribe=o??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new T(this.context,this.host,this.t,this.subscribe))}};var We=Lt`
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
  /* A Room without demand is idle, whatever the Plant around it is doing. */
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
  .zone-actions { display: flex; gap: 0.35rem; margin-block-start: 0.45rem; }
  .zone-actions button { min-inline-size: 2.75rem; }
  .preset { flex: 1; min-inline-size: 0; }
  .path-list, .actuator-list { display: grid; gap: 0.55rem; }
  .path { overflow: hidden; }
  .path-head { justify-content: space-between; flex-wrap: wrap; }
  .path-heading { display: flex; align-items: center; gap: 0.42rem; min-inline-size: 0; }
  .path-heading::before { content: ""; flex: 0 0 auto; inline-size: 0.43rem; block-size: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--_hy-text-muted) 55%, transparent); }
  /* A path takes the colour of its own Room's demand. */
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
  /* A Room card is the Room tile itself: the card frame replaces the tile's. */
  ha-card.room-card { padding: 0; }
  ha-card.room-card > .zone { border: 0; border-radius: inherit; box-shadow: none; }
  ha-card.room-card > .zone:not([data-demand="true"]) { background: transparent; }
  ha-card.room-card.compact > .zone { padding: 0.55rem; }
  ha-card.room-card > .notice, ha-card.room-card > .action-error { margin-block-start: 0.72rem; margin-inline: 0.72rem; }
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
`;var jn=O("hassConnection");var Bn=O("hassApi");var Wn=O("hassConfig");var Zn=O("hassInternationalization");var q=class extends _{static properties={preview:{type:Boolean},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_plant:{state:true},_actionError:{state:true}};static styles=We;_hass;_callService;_fromContext=new Set;_release;_followed;constructor(){super();this.preview=false;this._connection=void 0;this._unit=C;this._locale=void 0;this._localize=void 0;this._plant=H;this._actionError=null;new $(this,{context:jn,subscribe:true,callback:t=>{this._fromContext.add("connection");this._connection=t?.connection}});new $(this,{context:Bn,subscribe:true,callback:t=>{this._fromContext.add("api");this._callService=t?.callService}});new $(this,{context:Wn,subscribe:true,callback:t=>{this._fromContext.add("config");this._unit=gt(t?.config?.unit_system)}});new $(this,{context:Zn,subscribe:true,callback:t=>{this._fromContext.add("i18n");this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}})}set hass(t){this._hass=t;if(!this._fromContext.has("connection"))this._connection=t?.connection;if(!this._fromContext.has("api"))this._callService=t?(...e)=>t.callService(...e):void 0;if(!this._fromContext.has("config"))this._unit=gt(t?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}}get hass(){return this._hass}resetPlant(){this._plant=H;this._actionError=null}connectedCallback(){super.connectedCallback();this._follow()}disconnectedCallback(){this._unfollow();super.disconnectedCallback()}updated(t){super.updated(t);this._syncSelectValues();if(!this.isConnected)return;this._follow();if(this._connection&&(t.has("_connection")||this.preview))void v.load(this._connection)}_follow(){const t=this._connection;const e=this.plantId||void 0;const r=this._followed;if(r&&r.connection===t&&r.plantId===e)return;this._unfollow();if(!t||!e)return;this._followed={connection:t,plantId:e};this._release=z.subscribe(t,e,o=>{this._plant=o;this.plantStateChanged?.(o)})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._plant=H;this.plantStateChanged?.(H)}_syncSelectValues(){for(const t of this.renderRoot.querySelectorAll("select[data-value]")){const e=t.dataset.value??"";if(t.value!==e)t.value=e}}get renderContext(){return{unit:this._unit,locale:this._locale,localize:this._localize,moreInfo:t=>this.moreInfo(t),call:t=>this.call(t)}}moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:t}}))}call(t){const e=this._callService;if(!t||!e)return;e(t.domain,t.service,t.data,void 0,false).then(()=>{this._actionError=null},r=>{this._actionError=D(r,"The Home Assistant action failed.");this.requestUpdate()})}dismissActionError=()=>{this._actionError=null}};function Ze(n,t,e,r){const o=n.unit;if(t===null){return a`<div class=${r} part="metric"><span class="metric-value">--</span><span class="metric-label">${e}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${r} part="metric"><span class="metric-value">${bt(t,o,n.locale)}</span><span class="metric-unit">${o}</span><span class="metric-label">${e}</span></div>`}function Ke(n,t,e){const r=fe(t,e,n.unit);if(r!==null)n.call(ie(t,r))}function Kn(n,t,e){if(e===t.thermostat.hvac_mode)return;n.call(ae(t,e))}function Gn(n,t,e){n.call(se(t,e.target.value))}function st(n,t,e){const r=t.thermostat;const o=r.kind==="hydronicus";const i=G(t);const s=i!=="none";const u=r.hvac_mode==="off";const{unit:l,locale:d,localize:p}=n;const h=y(yt(l),d,l===C?1:0);const m=r.control_entity_id;const g=Boolean(m)&&r.target_temperature!==null;const S=me(t);const Gt=xt(t);const mt=r.hvac_mode?_t(p,r.hvac_mode):null;const an=u&&!t.blocked?mt??"Off":f(t.phase);const Xt=s?`${i==="cooling"?"Cooling":"Heating"} demand active`:u?"Thermostat off":"No demand";const ft=`zone-${t.id}`;const Yt=m?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>n.moreInfo(m)}>${t.name}</button>`:t.name;const ln=e.headingLevel===2?a`<h2 class="zone-title" part="room-title" id=${ft}>${Yt}</h2>`:a`<h4 class="zone-title" part="room-title" id=${ft}>${Yt}</h4>`;return a`<article class="zone" part="room" data-phase=${t.phase} data-hvac-mode=${r.hvac_mode??"unknown"} data-demand=${String(s)} data-demand-kind=${i} data-blocked=${String(t.blocked)} aria-labelledby=${ft}>
    <div class="row"><div>${ln}<p class="meta zone-owner">${o?"Hydronicus thermostat":`External thermostat \xB7 read-only${mt?` \xB7 ${mt}`:""}`}</p></div><span class=${`phase${t.blocked?" state blocked":""}${u?" off":""}`} part="badge">${an}</span></div>
    <div class="temperature-panel">
      ${Ze(n,r.current_temperature,"Current","metric")}
      ${Ze(n,r.target_temperature,"Target","metric target")}
    </div>
    <p class="meta zone-note" dir="auto">${o?Xt:`${Xt} \xB7 ${r.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Room diagnostics">
      <li part="chip" class="diagnostic-chip" dir="auto">${y(t.sensor_status.usable,d,0)} sensor${t.sensor_status.usable===1?"":"s"} ready</li>
      ${t.sensor_status.optional_excluded?a`<li part="chip" class="diagnostic-chip warning" dir="auto">${y(t.sensor_status.optional_excluded,d,0)} optional excluded</li>`:c}
      ${t.sensor_status.required_blocking?a`<li part="chip" class="diagnostic-chip danger" dir="auto">${y(t.sensor_status.required_blocking,d,0)} required blocked</li>`:c}
      ${t.cooling.dew_point===null?c:a`<li part="chip" class="diagnostic-chip" dir="auto">Dew point ${bt(t.cooling.dew_point,l,d)} ${l}</li>`}
      ${t.cooling.condensation_margin===null?c:a`<li part="chip" class="diagnostic-chip ${t.cooling.blocked?"danger":""}" dir="auto">Margin ${te(t.cooling.condensation_margin,l,d)} ${l}</li>`}
    </ul>
    ${r.preset&&r.preset!=="none"?a`<p class="meta zone-note" dir="auto">Preset: ${f(r.preset)}</p>`:c}
    ${t.blocked_reason?a`<p class="meta zone-note" dir="auto">${t.blocked_reason}</p>`:c}
    ${t.coupling_group_ids.length?a`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>`:c}
    ${o?a`${Gt.length?a`<div class="hvac-modes" part="control" role="group" aria-label=${`${t.name} HVAC mode`}>${Gt.map(x=>a`<button type="button" class="hvac-mode" part="segment" data-mode=${x} aria-pressed=${String(x===r.hvac_mode)} ?disabled=${!m} @click=${()=>Kn(n,t,x)}>${_t(p,x)}</button>`)}</div>`:c}
          <div class="zone-actions" part="controls">
            <button type="button" part="control" dir="ltr" ?disabled=${!g} aria-label=${`Decrease ${t.name} target by ${h} ${l}`} @click=${()=>Ke(n,t,-1)}>−${h}</button>
            <button type="button" part="control" dir="ltr" ?disabled=${!g} aria-label=${`Increase ${t.name} target by ${h} ${l}`} @click=${()=>Ke(n,t,1)}>+${h}</button>
            ${S.length?a`<select class="preset" part="control" data-value=${r.preset??"none"} aria-label=${`${t.name} preset`} ?disabled=${!m} @change=${x=>Gn(n,t,x)}>${["none",...S].map(x=>a`<option value=${x}>${f(x)}</option>`)}</select>`:c}
          </div>`:a`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`}var Zt=["auto","idle","heating","cooling"];function Xn(n,t){const e=t.plant;const r=`Mode ${N(n.localize,"select.requested_mode",e.requested_mode)}`;if(e.requested_mode==="auto"||e.requested_mode===e.active_mode)return r;return`${r} \xB7 now ${N(n.localize,"sensor.operating_mode",e.active_mode)}`}function Ge(n,t,e){const r=t.plant;const o=r.execution_boundary;const i=t.controls.requested_mode;const s=Zt.includes(r.requested_mode)?Zt:[...Zt,r.requested_mode];const u=he(t);const l=d=>n.call(le(t,d.target.value));return a`<header class="header" part="header">
      <div class="plant-heading">
        <span class="plant-mark" part="mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow" part="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title" part="title">${i?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>n.moreInfo(i)}>${r.name}</button>`:r.name}</h2>
          <div class="status-line" part="status">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${N(n.localize,"sensor.controller_status",r.status)}</span>
            <span class="meta mode-detail">${Xn(n,t)}</span>
          </div>
          ${u===null?c:a`<p class="meta source-line" dir="auto"><strong>Source</strong> ${u}</p>`}
          <p class="meta" dir="auto">${r.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls" part="controls">
        <span class="badge ${ue(o)}" part="badge"><span class="visually-hidden">Execution boundary: </span>${wt(o)}</span>
        <label class="mode-control" part="control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${r.requested_mode} ?disabled=${!i} @change=${l}>
          ${s.map(d=>a`<option value=${d}>${N(n.localize,"select.requested_mode",d)}</option>`)}
        </select></label>
        ${e}
      </div>
    </header>`}function Xe(n){return a`<div class="boundary" part="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${n.plant.execution_boundary.message||`${wt(n.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`}function Ye(n,t){const e=ne(t);if(!e.length)return c;return a`<section part="section" aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${y(e.length,n.locale,0)}</span></div>${e.slice(0,3).map(r=>{const o=r.severity==="error"||r.severity==="critical";return a`<p class="alert ${o?"error":""}" part="notice" data-severity=${r.severity} dir="auto"><strong>${pe(r)}</strong><span> · ${r.message}</span></p>`})}</section>`}function Je(n,t){return a`<section part="section" aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${y(t.zones.length,n.locale,0)} visible</span></div><div class="zone-grid">${t.zones.length?t.zones.map(e=>st(n,e,{headingLevel:4})):a`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`}function Qe(n){if(!n.delivery_paths.length)return c;return a`<section part="section" aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${n.delivery_paths.map(t=>{const e=n.zones.find(r=>r.id===t.zone_id);return a`<article class="path" part="path" data-status=${t.status} data-flowing=${String(vt(t.status))} data-demand-kind=${G(e)}>
    <div class="path-head"><div class="path-heading"><strong>${e?.name??t.zone_id}</strong></div><div class="status-line"><span class="state ${t.status}" part="badge">${f(t.status)}</span>${t.coupled?a`<span class="meta">shares equipment</span>`:c}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${t.nodes.map((r,o)=>a`<li class="path-step">${o?a`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" part="node" data-kind=${r.kind} data-state=${r.state} data-flowing=${String(vt(r.state))}><span class="node-kind">${$t(r.kind)}</span><span class="node-name">${r.name}</span><span class="node-state">${f(r.state)}</span></span></li>`)}</ol>
    ${t.problem?a`<p class="meta path-problem" dir="auto">${t.problem}</p>`:c}
  </article>`})}</div></section>`}function tn(n){if(!n.actuators.length)return c;return a`<section part="section" aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 part="section-title" id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${n.actuators.map(t=>a`<article class="actuator" part="equipment" data-state=${t.state}><div class="row"><strong>${t.name}</strong><span class="state actuator-state ${t.state}" part="badge">${f(t.state)}</span></div><p class="meta" dir="auto">${f(t.kind)} · ${t.reason??"No additional explanation."}</p>${t.active_consumers.length?a`<ul class="consumer-list" aria-label="Loops using this equipment">${t.active_consumers.map(e=>a`<li class="consumer-chip" part="chip" title=${e.id}><strong>${e.name}</strong></li>`)}</ul>`:a`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}function en(n){return a`<section part="section"><details part="disclosure"><summary>Controller explanations</summary>${n.explanations.map(t=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${t.name??$t(t.scope)}</strong> · ${t.message}</p></div>`)}</details></section>`}function nn(n,t){const e=Object.values(t.execution.operations).flat();if(!e.length)return c;return a`<section part="section"><details part="disclosure" open><summary>Latest operation outcomes (${y(e.length,n.locale,0)})</summary>${e.map(r=>{const o=String(r.result??"unknown");return a`<div class="operation" data-result=${o}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${de(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}function rn(n){return`Retrying in ${Math.round(n/1e3)} s.`}function b(n,t,e,r,o){return a`<ha-card part="card" class="state-card" data-visual=${r==="alert"?"attention":"idle"}>
    <div class="plant-heading"><span class="plant-mark" part="mark" aria-hidden="true"></span><div><p class="eyebrow" part="eyebrow">${n}</p><h2 part="title">${t}</h2></div></div>
    <p class=${r==="alert"?"notice error":"notice"} part="notice" role=${r} dir="auto">${e}</p>
    ${o?a`<p class="meta" dir="auto">${o}</p>`:c}
  </ha-card>`}function Yn(n){return a`<ha-card part="card" class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${n?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
  </ha-card>`}function at(n){return n.snapshotError?null:n.snapshot}function lt(n,t){if(t.snapshotError){return b(n,"Card update needed",t.snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const e=t.status;switch(e.kind){case"not_found":return b(n,"Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return b(n,"No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return b(n,"Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return b(n,"Connection needs attention",e.message,"alert",rn(e.delayMs));default:return Yn(e.kind==="reconnecting")}}function ct(n){if(n.kind==="reconnecting"){return a`<p class="notice" part="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(n.kind==="retrying"){return a`<p class="notice" part="notice" role="status" dir="auto">${n.message} ${rn(n.delayMs)} The values below may be out of date.</p>`}return c}function dt(n,t){if(!n)return c;return a`<div class="action-error" part="notice" role="alert"><span dir="auto">${n}</span><button type="button" part="control" @click=${t}>Dismiss</button></div>`}var Jn=1200;var Kt="Hydronicus Plant";var Qn=["rooms","paths","equipment"];function tr(n,t){switch(n){case"header":return 4;case"alerts":{const e=Math.min(t.alerts.length,3);return e?1+e:0}case"rooms":return 1+Math.max(1,t.zones.length)*5;case"paths":return t.delivery_paths.length?1+t.delivery_paths.length*3:0;case"equipment":return t.actuators.length?1+t.actuators.length*2:0;case"explanations":return 1;case"operations":{const e=Object.values(t.execution.operations).flat().length;return e?1+e:0}}}var ut=class extends q{static properties={_config:{state:true},_holdingShutdown:{state:true}};_holdTimer=null;constructor(){super();this._config=void 0;this._holdingShutdown=false}static async getConfigForm(){return Ce()}static async getStubConfig(t){return $e(t)}setConfig(t){const e=Rt(t);if(e.plant!==this._config?.plant)this.resetPlant();this._config=e}get plantId(){return this._config?.plant}getCardSize(){const t=this._plant.snapshot;const e=tt(this._config);if(!t)return e.includes("header")?4:2;return Math.max(1,e.reduce((r,o)=>r+tr(o,t),0))}getGridOptions(){const t=tt(this._config).some(e=>Qn.includes(e));return t?{columns:12,min_columns:6}:{columns:6,min_columns:4}}disconnectedCallback(){this._clearHold();super.disconnectedCallback()}plantStateChanged(t){if(!t.snapshot)this._clearHold()}render(){const t=this._config;if(!t||!t.plant){return b(Kt,Kt,"Select a Hydronicus Plant in the card editor.","status")}const e=this._plant;const r=at(e);if(!r)return lt(Kt,e);const o=this.renderContext;const i=tt(t);const s=a`${ct(e.status)}${dt(this._actionError,this.dismissActionError)}`;return a`<ha-card part="card" class=${t.density??"comfortable"} data-visual=${re(r)}>
      ${i.includes("header")?c:s}
      ${i.map(u=>this._renderSection(u,o,r,s))}
    </ha-card>`}_renderSection(t,e,r,o){switch(t){case"header":return a`${Ge(e,r,this._renderShutdown(r))}
          ${o}
          ${Xe(r)}`;case"alerts":return Ye(e,r);case"rooms":return Je(e,r);case"paths":return Qe(r);case"equipment":return tn(r);case"explanations":return en(r);case"operations":return nn(e,r)}}_renderShutdown(t){const e=!t.controls.safe_shutdown;const r=t.plant.execution_boundary.dry_run;return a`<button type="button" part="control" class=${`shutdown${r?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${e} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_startHold(){if(!this._plant.snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;const t=this._plant.snapshot;if(t)this.call(ce(t))},Jn)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=t=>{if(t.button!==void 0&&t.button>0)return;this._startHold()};_keyHoldStart=t=>{if(t.key!=="Enter"&&t.key!==" ")return;t.preventDefault();if(!t.repeat)this._startHold()};_keyHoldEnd=t=>{if(t.key==="Enter"||t.key===" ")this._clearHold()};_preventContextMenu=t=>{t.preventDefault()}};var U="Hydronicus Room";var ht=class extends q{static properties={_config:{state:true}};constructor(){super();this._config=void 0}static getConfigElement(){return document.createElement(Q)}static async getStubConfig(t){return ke(t)}setConfig(t){const e=et(t);if(e.plant!==this._config?.plant)this.resetPlant();else if(e.room!==this._config?.room)this._actionError=null;this._config=e}get plantId(){return this._config?.room?this._config.plant:void 0}getCardSize(){return 5}getGridOptions(){return{columns:6,min_columns:4}}render(){const t=this._config;if(!t||!t.plant){return b(U,U,"Select a Hydronicus Plant and a Room in the card editor.","status")}if(!t.room){return b(U,U,"Select a Room in the card editor.","status")}const e=this._plant;const r=at(e);if(!r)return lt(U,e);const o=r.zones.find(i=>i.id===t.room);if(!o){return b(U,"Room not found","This Room is not in the Plant, or you do not have access to it. Choose another Room in the card editor.","alert")}return a`<ha-card part="card" class="room-card ${t.density??"comfortable"}" data-visual=${oe(o)}>
      ${ct(e.status)}
      ${dt(this._actionError,this.dismissActionError)}
      ${st(this.renderContext,o,{headingLevel:2})}
    </ha-card>`}};var pt=class extends _{static properties={hass:{attribute:false},_config:{state:true},_plants:{state:true},_rooms:{state:true}};_release;_followed;_directoryConnection;constructor(){super();this.hass=void 0;this._config=void 0;this._plants=v.known;this._rooms=[]}setConfig(t){et(t);this._config=t}connectedCallback(){super.connectedCallback();this.requestUpdate()}disconnectedCallback(){this._unfollow();this._directoryConnection=void 0;super.disconnectedCallback()}updated(t){super.updated(t);if(!this.isConnected)return;const e=this.hass?.connection;if(e&&e!==this._directoryConnection){this._directoryConnection=e;void v.load(e).then(r=>{this._plants=r})}this._follow(e,this._config?.plant||void 0)}_follow(t,e){const r=this._followed;if(r?.connection===t&&r?.plantId===e)return;this._unfollow();if(!t||!e)return;this._followed={connection:t,plantId:e};this._release=z.subscribe(t,e,o=>{if(o.snapshot)this._rooms=o.snapshot.zones.map(i=>({id:i.id,name:i.name}))})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._rooms=[]}render(){return a`<ha-form
      .hass=${this.hass}
      .data=${this._config??{}}
      .schema=${Ae(this._plants,this._rooms)}
      .computeLabel=${Tt}
      .computeHelper=${Ht}
      @value-changed=${this._valueChanged}
    ></ha-form>`}_valueChanged(t){t.stopPropagation();const e={...t.detail.value};if(e.plant!==this._config?.plant)e.room="";this._config=e;this.dispatchEvent(new CustomEvent("config-changed",{bubbles:true,composed:true,detail:{config:e}}))}};var er=[[Y,ut],[J,ht],[Q,pt]];function on(n){for(const[t,e]of er){if(!n.get(t))n.define(t,e)}}var sn=window.customElements;on(sn);void sn.whenDefined("home-assistant").then(()=>{on(window.customElements)});var nr=[{type:Y,name:"Hydronicus Plant",description:"Topology-driven Hydronicus Plant status and controls.",preview:false},{type:J,name:"Hydronicus Room",description:"One Room of a Hydronicus Plant, with its thermostat and controls.",preview:true}];window.customCards=window.customCards??[];for(const n of nr){if(window.customCards.some(t=>t.type===n.type))continue;window.customCards.push({...n,version:"0.1.0-rc.6",documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
