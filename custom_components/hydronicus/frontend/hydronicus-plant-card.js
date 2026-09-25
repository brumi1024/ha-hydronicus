var C="\xB0C";var ln=5;var cn=35;function fe(n){return n?.temperature==="\xB0F"?"\xB0F":C}function Y(n,e){return e==="\xB0F"?n*9/5+32:n}function dn(n,e){return e==="\xB0F"?n*9/5:n}function ge(n){return n==="\xB0F"?1:.5}function Je(n,e,t){const r=ge(t);const o=Y(n,t);const s=o/r;const i=(e>0?Math.floor(s+1e-9)+1:Math.ceil(s-1e-9)-1)*r;const u=Y(ln,t);const l=Y(cn,t);return Number(Math.min(l,Math.max(u,i)).toFixed(1))}function un(n){switch(n?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return n?.language}}var Xe=new Map;function y(n,e,t=1){const r=un(e);const o=e?.number_format!=="none";const s=`${JSON.stringify(r)}|${t}|${o}`;let i=Xe.get(s);if(!i){try{i=new Intl.NumberFormat(r,{minimumFractionDigits:t,maximumFractionDigits:t,useGrouping:o})}catch{i=new Intl.NumberFormat(void 0,{minimumFractionDigits:t,maximumFractionDigits:t})}Xe.set(s,i)}return i.format(n)}function ye(n,e,t){return y(Y(n,e),t)}function Qe(n,e,t){return y(dn(n,e),t)}var hn=2;var pn=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function et(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const e=n;if(e.schema_version!==hn){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(e.schema_version)}.`)}if(!e.plant||!Array.isArray(e.zones)||!Array.isArray(e.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return e}function tt(n){return[...n.alerts].sort((e,t)=>e.priority-t.priority||e.code.localeCompare(t.code)||e.scope.localeCompare(t.scope))}function nt(n){const e=n.plant.health.toLowerCase();const t=n.alerts.some(o=>o.severity==="critical"||o.severity==="error");if(n.safe_shutdown.active||t||["blocked","critical","error","failed","unhealthy"].includes(e)){return"attention"}const r=`${n.plant.active_mode} ${n.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function rt(n){if(n.blocked)return"attention";if(n.cooling.demand)return"cooling";if(n.demand)return"heating";return"idle"}function be(n){return pn.has(n.toLowerCase())}function ot(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:n.thermostat.control_entity_id,temperature:e}}}function st(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:n.thermostat.control_entity_id,preset_mode:e}}}function it(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;if(!_e(n).includes(e))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:n.thermostat.control_entity_id,hvac_mode:e}}}function at(n,e){if(!n.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:n.controls.requested_mode,option:e}}}function lt(n){if(!n.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:n.controls.safe_shutdown}}}function ct(n){const e=String(n.action??"operation").replaceAll("_"," ");const t=String(n.actuator_name??"actuator");const r=String(n.result??"");if(r==="proposed")return`Would ${e} ${t}`;if(r==="executed")return`Executed ${t} ${e}`;if(r==="suppressed")return`Suppressed ${t} ${e}`;return`${r||"Operation"}: ${t} ${e}`}function mn(n){return n.replaceAll("_"," ")}function N(n,e,t){const[r,o]=e.split(".");return n?.(`component.hydronicus.entity.${r}.${o}.state.${t}`)||f(t)}function f(n){const e=mn(n);return e.charAt(0).toUpperCase()+e.slice(1)}var fn={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function ve(n,e){return n?.(`component.climate.entity_component._.state.${e}`)||fn[e]||f(e)}function _e(n){if(n.thermostat.kind!=="hydronicus")return[];return[...new Set(n.thermostat.hvac_modes??[])]}function xe(n){if(n.dry_run||n.mode==="dry_run")return"Dry run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"Live";return f(n.mode)}function dt(n){if(n.dry_run||n.mode==="dry_run")return"dry-run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"live";return n.mode.replaceAll("_","-")}function ut(n){const{active_name:e,recommended_name:t}=n.plant.source;if(!n.sources.length&&!e&&!t)return null;const r=[e??"None active"];if(t&&t!==e)r.push(`recommended ${t}`);return r.join(" \xB7 ")}var gn={zone:"Room",circuit:"Loop"};var yn={plant_initializing:"Starting",plant_unavailable:"Plant unavailable",binding_unavailable:"Entity unavailable",zone_sensor_blocked:"Sensor blocked",zone_mode_blocked:"Room blocked",cooling_blocked:"Cooling blocked",actuator_mismatch:"Equipment mismatch",actuator_blocked:"Equipment blocked",mode_changeover:"Mode changeover"};function ht(n){const e=yn[n.code]??f(n.code);return n.scope!=="plant"&&n.name?`${n.name} \xB7 ${e}`:e}function $e(n){return gn[n]??f(n)}function pt(n){return[...new Set(n.thermostat.preset_modes)].filter(e=>e!=="none")}function mt(n,e,t=C){if(n.thermostat.target_temperature===null)return null;return Je(n.thermostat.target_temperature,e,t)}var bn="hydronicus/subscribe_plant";var vn=1e3;var _n=6e4;var xn={setTimeout:(n,e)=>globalThis.setTimeout(n,e),clearTimeout:n=>globalThis.clearTimeout(n)};var ft={plant_not_found:"not_found",unauthorized:"unauthorized"};function gt(n){return n!==void 0&&Object.hasOwn(ft,n)?ft[n]:void 0}function $n(n){return typeof n==="object"&&n!==null&&"code"in n?String(n.code):void 0}function D(n,e){if(n instanceof Error)return n.message;if(typeof n==="object"&&n!==null&&"message"in n&&n.message){return String(n.message)}return e}function we(n){if(!n)return;try{void Promise.resolve(n()).catch(()=>void 0)}catch{}}var G=class{constructor(e,t=xn){this.host=e;this.scheduler=t}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(e,t){if(e===this.connection&&t===this.plantId)return;this.disconnect();if(!e||!t)return;this.connection=e;this.plantId=t;e.addEventListener?.("disconnected",this.handleDisconnected);e.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;we(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const e=this.connection;const t=this.plantId;if(!e||!t)return;this.cancelRetry();const r=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}e.subscribeMessage(o=>this.handleEvent(r,o),{type:bn,plant_id:t},{resubscribe:false}).then(o=>{if(r!==this.generation){we(o);return}this.unsubscribe=o}).catch(o=>{if(r!==this.generation)return;this.handleError(o)})}handleEvent(e,t){if(e!==this.generation)return;if(t.snapshot!==void 0&&t.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(t.snapshot);return}if(t.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const r=gt(t.status);if(r)this.stop({kind:r})}handleError(e){const t=gt($n(e));if(t){this.stop({kind:t});return}const r=Math.min(vn*2**this.attempt,_n);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:r,message:D(e,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},r)}stop(e){this.cancelRetry();this.generation+=1;we(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(e)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(e){this.current=e;this.host.onStatus(e)}};var H={status:{kind:"idle"},snapshot:null,snapshotError:null};var wn=new Set(["idle","unavailable","not_found","unauthorized"]);var Se=class{listeners=new Set;current=H;stream;constructor(e){this.stream=new G({onStatus:t=>this.statusChanged(t),onSnapshot:t=>this.snapshotReceived(t)},e)}get state(){return this.current}open(e,t){this.stream.connect(e,t)}close(){this.stream.disconnect()}statusChanged(e){const t=wn.has(e.kind)?null:this.current.snapshot;this.publish({...this.current,status:e,snapshot:t})}snapshotReceived(e){try{this.publish({...this.current,snapshot:et(e),snapshotError:null})}catch(t){this.publish({...this.current,snapshot:null,snapshotError:D(t,"Unsupported Hydronicus snapshot.")})}}publish(e){this.current=e;for(const t of[...this.listeners])t(e)}};var ke=class{constructor(e){this.scheduler=e}scheduler;feeds=new WeakMap;subscribe(e,t,r){let o=this.feeds.get(e);if(!o){o=new Map;this.feeds.set(e,o)}let s=o.get(t);const i=!s;if(!s){s=new Se(this.scheduler);o.set(t,s)}s.listeners.add(r);if(i)s.open(e,t);else r(s.state);const u=o;const l=s;let d=false;return()=>{if(d)return;d=true;l.listeners.delete(r);if(l.listeners.size)return;queueMicrotask(()=>{if(l.listeners.size||u.get(t)!==l)return;u.delete(t);l.close()})}}snapshot(e,t,r=2e3){return new Promise(o=>{let s=false;const i=d=>{if(s)return;s=true;clearTimeout(u);queueMicrotask(()=>l());o(d)};const u=setTimeout(()=>i(null),r);const l=this.subscribe(e,t,d=>{if(d.snapshot)i(d.snapshot);else if(["not_found","unauthorized"].includes(d.status.kind)||d.snapshotError)i(null)})})}};var z=new ke;var K="hydronicus-plant-card";var yt=`custom:${K}`;var X="hydronicus-room-card";var bt=`custom:${X}`;var J="hydronicus-room-card-editor";var Sn="hydronicus/list_plants";var kn=["comfortable","compact"];var vt=[{value:"header",label:"Header and execution boundary"},{value:"alerts",label:"Alerts"},{value:"rooms",label:"Rooms"},{value:"paths",label:"Hydraulic flow"},{value:"equipment",label:"Equipment"},{value:"explanations",label:"Controller explanations"},{value:"operations",label:"Operation outcomes"}];var Ce=vt.map(n=>n.value);function _t(n,e,t){if(!n||typeof n!=="object"){throw new Error(`${e} requires a configuration.`)}const r=n;if(r.type!==t){throw new Error(`${e} type must be ${t}.`)}if(typeof r.plant!=="string"){throw new Error(`${e} requires one Plant UUID in \`plant\`.`)}return r}function xt(n,e){const t=n??"comfortable";if(!kn.includes(t)){throw new Error(`${e} density must be comfortable or compact.`)}return t}function Cn(n){if(n===void 0||n===null)return void 0;if(!Array.isArray(n)){throw new Error("Hydronicus Plant card `sections` must be a list of section names.")}const e=new Set;for(const t of n){if(typeof t!=="string"||!Ce.includes(t)){throw new Error(`Hydronicus Plant card section ${JSON.stringify(t)} is unknown. Use ${Ce.join(", ")}.`)}if(e.has(t)){throw new Error(`Hydronicus Plant card section ${t} is listed twice.`)}e.add(t)}return n.length?n:void 0}function Pe(n){const e="Hydronicus Plant card";const t=_t(n,e,yt);const r=xt(t.density,e);const o=Cn(t.sections);return{type:yt,plant:t.plant.trim(),density:r,...o?{sections:o}:{}}}function Q(n){return n?.sections??Ce}function ee(n){const e="Hydronicus Room card";const t=_t(n,e,bt);const r=t.room??"";if(typeof r!=="string"){throw new Error(`${e} requires one Room id in \`room\`.`)}const o=xt(t.density,e);return{type:bt,plant:t.plant.trim(),room:r.trim(),density:o}}var Ae=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(e){if(this.connection===e&&this.pending)return this.pending;this.connection=e;this.pending=e.sendMessagePromise({type:Sn}).then(t=>{this.plants=Array.isArray(t.plants)?t.plants:[];return this.plants}).catch(()=>{if(this.connection===e)this.pending=null;return this.plants});return this.pending}async settled(e=2e3){if(!this.pending)return this.plants;let t;const r=new Promise(o=>{t=setTimeout(()=>o(this.plants),e)});try{return await Promise.race([this.pending,r])}finally{clearTimeout(t)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var v=new Ae;async function $t(n){const e=n?.connection?await v.load(n.connection):v.known;return{plant:e[0]?.id??"",density:"comfortable"}}async function wt(n){const e=n?.connection;const t=e?await v.load(e):v.known;const r=t[0]?.id??"";const o=e&&r?await z.snapshot(e,r):null;return{plant:r,room:o?.zones[0]?.id??"",density:"comfortable"}}var An={plant:"Hydronicus Plant",room:"Room",density:"Density",sections:"Sections"};var En={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",room:"The Room this card shows. Only Rooms you can read are listed; one that is not listed shows its id.",density:"Compact uses less spacing for dense dashboards.",sections:"The parts of the Plant to show, in this order. Leave empty to show every section."};var Re=n=>An[n.name];var Te=n=>En[n.name];function Ee(n){if(n.length===0)return{text:{}};return{select:{mode:"dropdown",options:n.map(e=>({value:e.id,label:e.name}))}}}var St={name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}};async function kt(){const n=await v.settled();return{schema:[{name:"plant",required:true,selector:Ee(n)},St,{name:"sections",selector:{select:{multiple:true,reorder:true,mode:"dropdown",options:vt.map(e=>({...e}))}}}],computeLabel:Re,computeHelper:Te,assertConfig:e=>{Pe(e)}}}function Ct(n,e){return[{name:"plant",required:true,selector:Ee(n)},{name:"room",required:true,selector:Ee(e)},St]}var te=globalThis;var ne=te.ShadowRoot&&(void 0===te.ShadyCSS||te.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var He=Symbol();var At=new WeakMap;var I=class{constructor(e,t,r){if(this._$cssResult$=true,r!==He)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(ne&&void 0===e){const r=void 0!==t&&1===t.length;r&&(e=At.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&At.set(t,e))}return e}toString(){return this.cssText}};var Et=n=>new I("string"==typeof n?n:n+"",void 0,He);var ze=(n,...e)=>{const t=1===n.length?n[0]:e.reduce((r,o,s)=>r+(i=>{if(true===i._$cssResult$)return i.cssText;if("number"==typeof i)return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[s+1],n[0]);return new I(t,n,He)};var Pt=(n,e)=>{if(ne)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const t of e){const r=document.createElement("style"),o=te.litNonce;void 0!==o&&r.setAttribute("nonce",o),r.textContent=t.cssText,n.appendChild(r)}};var Le=ne?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(const r of e.cssRules)t+=r.cssText;return Et(t)})(n):n;var{is:Pn,defineProperty:Rn,getOwnPropertyDescriptor:Tn,getOwnPropertyNames:Hn,getOwnPropertySymbols:zn,getPrototypeOf:Ln}=Object;var re=globalThis;var Rt=re.trustedTypes;var Mn=Rt?Rt.emptyScript:"";var On=re.reactiveElementPolyfillSupport;var F=(n,e)=>n;var Me={toAttribute(n,e){switch(e){case Boolean:n=n?Mn:null;break;case Object:case Array:n=null==n?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=null!==n;break;case Number:t=null===n?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch(r){t=null}}return t}};var Ht=(n,e)=>!Pn(n,e);var Tt={attribute:true,type:String,converter:Me,reflect:false,useDefault:false,hasChanged:Ht};Symbol.metadata??=Symbol("metadata"),re.litPropertyMetadata??=new WeakMap;var $=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Tt){if(t.state&&(t.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=true),this.elementProperties.set(e,t),!t.noAccessor){const r=Symbol(),o=this.getPropertyDescriptor(e,r,t);void 0!==o&&Rn(this.prototype,e,o)}}static getPropertyDescriptor(e,t,r){const{get:o,set:s}=Tn(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:o,set(i){const u=o?.call(this);s?.call(this,i),this.requestUpdate(e,u,r)},configurable:true,enumerable:true}}static getPropertyOptions(e){return this.elementProperties.get(e)??Tt}static _$Ei(){if(this.hasOwnProperty(F("elementProperties")))return;const e=Ln(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(F("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(F("properties"))){const t=this.properties,r=[...Hn(t),...zn(t)];for(const o of r)this.createProperty(o,t[o])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[r,o]of t)this.elementProperties.set(r,o)}this._$Eh=new Map;for(const[t,r]of this.elementProperties){const o=this._$Eu(t,r);void 0!==o&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const r=new Set(e.flat(1/0).reverse());for(const o of r)t.unshift(Le(o))}else void 0!==e&&t.push(Le(e));return t}static _$Eu(e,t){const r=t.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Pt(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){const r=this.constructor.elementProperties.get(e),o=this.constructor._$Eu(e,r);if(void 0!==o&&true===r.reflect){const s=(void 0!==r.converter?.toAttribute?r.converter:Me).toAttribute(t,r.type);this._$Em=e,null==s?this.removeAttribute(o):this.setAttribute(o,s),this._$Em=null}}_$AK(e,t){const r=this.constructor,o=r._$Eh.get(e);if(void 0!==o&&this._$Em!==o){const s=r.getPropertyOptions(o),i="function"==typeof s.converter?{fromAttribute:s.converter}:void 0!==s.converter?.fromAttribute?s.converter:Me;this._$Em=o;const u=i.fromAttribute(t,s.type);this[o]=u??this._$Ej?.get(o)??u,this._$Em=null}}requestUpdate(e,t,r,o=false,s){if(void 0!==e){const i=this.constructor;if(false===o&&(s=this[e]),r??=i.getPropertyOptions(e),!((r.hasChanged??Ht)(s,t)||r.useDefault&&r.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,r))))return;this.C(e,t,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:o,wrapped:s},i){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),true!==s||void 0!==i)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),true===o&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(t){Promise.reject(t)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[o,s]of this._$Ep)this[o]=s;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[o,s]of r){const{wrapped:i}=s,u=this[o];true!==i||this._$AL.has(o)||void 0===u||this.C(o,void 0,s,u)}}let e=false;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=false,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return true}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};$.elementStyles=[],$.shadowRootOptions={mode:"open"},$[F("elementProperties")]=new Map,$[F("finalized")]=new Map,On?.({ReactiveElement:$}),(re.reactiveElementVersions??=[]).push("2.1.2");var Fe=globalThis;var zt=n=>n;var oe=Fe.trustedTypes;var Lt=oe?oe.createPolicy("lit-html",{createHTML:n=>n}):void 0;var Dt="$lit$";var S=`lit$${Math.random().toFixed(9).slice(2)}$`;var It="?"+S;var Un=`<${It}>`;var P=document;var j=()=>P.createComment("");var B=n=>null===n||"object"!=typeof n&&"function"!=typeof n;var Ve=Array.isArray;var qn=n=>Ve(n)||"function"==typeof n?.[Symbol.iterator];var Oe="[ 	\n\f\r]";var V=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Mt=/-->/g;var Ot=/>/g;var A=RegExp(`>|${Oe}(?:([^\\s"'>=/]+)(${Oe}*=${Oe}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Ut=/'/g;var qt=/"/g;var Ft=/^(?:script|style|textarea|title)$/i;var je=n=>(e,...t)=>({_$litType$:n,strings:e,values:t});var a=je(1);var fr=je(2);var gr=je(3);var R=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var Nt=new WeakMap;var E=P.createTreeWalker(P,129);function Vt(n,e){if(!Ve(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Lt?Lt.createHTML(e):e}var Nn=(n,e)=>{const t=n.length-1,r=[];let o,s=2===e?"<svg>":3===e?"<math>":"",i=V;for(let u=0;u<t;u++){const l=n[u];let d,p,h=-1,m=0;for(;m<l.length&&(i.lastIndex=m,p=i.exec(l),null!==p);)m=i.lastIndex,i===V?"!--"===p[1]?i=Mt:void 0!==p[1]?i=Ot:void 0!==p[2]?(Ft.test(p[2])&&(o=RegExp("</"+p[2],"g")),i=A):void 0!==p[3]&&(i=A):i===A?">"===p[0]?(i=o??V,h=-1):void 0===p[1]?h=-2:(h=i.lastIndex-p[2].length,d=p[1],i=void 0===p[3]?A:'"'===p[3]?qt:Ut):i===qt||i===Ut?i=A:i===Mt||i===Ot?i=V:(i=A,o=void 0);const g=i===A&&n[u+1].startsWith("/>")?" ":"";s+=i===V?l+Un:h>=0?(r.push(d),l.slice(0,h)+Dt+l.slice(h)+S+g):l+S+(-2===h?u:g)}return[Vt(n,s+(n[t]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),r]};var W=class n{constructor({strings:e,_$litType$:t},r){let o;this.parts=[];let s=0,i=0;const u=e.length-1,l=this.parts,[d,p]=Nn(e,t);if(this.el=n.createElement(d,r),E.currentNode=this.el.content,2===t||3===t){const h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;null!==(o=E.nextNode())&&l.length<u;){if(1===o.nodeType){if(o.hasAttributes())for(const h of o.getAttributeNames())if(h.endsWith(Dt)){const m=p[i++],g=o.getAttribute(h).split(S),k=/([.?@])?(.*)/.exec(m);l.push({type:1,index:s,name:k[2],strings:g,ctor:"."===k[1]?qe:"?"===k[1]?Ne:"@"===k[1]?De:M}),o.removeAttribute(h)}else h.startsWith(S)&&(l.push({type:6,index:s}),o.removeAttribute(h));if(Ft.test(o.tagName)){const h=o.textContent.split(S),m=h.length-1;if(m>0){o.textContent=oe?oe.emptyScript:"";for(let g=0;g<m;g++)o.append(h[g],j()),E.nextNode(),l.push({type:2,index:++s});o.append(h[m],j())}}}else if(8===o.nodeType)if(o.data===It)l.push({type:2,index:s});else{let h=-1;for(;-1!==(h=o.data.indexOf(S,h+1));)l.push({type:7,index:s}),h+=S.length-1}s++}}static createElement(e,t){const r=P.createElement("template");return r.innerHTML=e,r}};function L(n,e,t=n,r){if(e===R)return e;let o=void 0!==r?t._$Co?.[r]:t._$Cl;const s=B(e)?void 0:e._$litDirective$;return o?.constructor!==s&&(o?._$AO?.(false),void 0===s?o=void 0:(o=new s(n),o._$AT(n,t,r)),void 0!==r?(t._$Co??=[])[r]=o:t._$Cl=o),void 0!==o&&(e=L(n,o._$AS(n,e.values),o,r)),e}var Ue=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:r}=this._$AD,o=(e?.creationScope??P).importNode(t,true);E.currentNode=o;let s=E.nextNode(),i=0,u=0,l=r[0];for(;void 0!==l;){if(i===l.index){let d;2===l.type?d=new Z(s,s.nextSibling,this,e):1===l.type?d=new l.ctor(s,l.name,l.strings,this,e):6===l.type&&(d=new Ie(s,this,e)),this._$AV.push(d),l=r[++u]}i!==l?.index&&(s=E.nextNode(),i++)}return E.currentNode=P,o}p(e){let t=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}};var Z=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,o){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??true}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=L(this,e,t),B(e)?e===c||null==e||""===e?(this._$AH!==c&&this._$AR(),this._$AH=c):e!==this._$AH&&e!==R&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):qn(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==c&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:r}=e,o="number"==typeof r?this._$AC(e):(void 0===r.el&&(r.el=W.createElement(Vt(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(t);else{const s=new Ue(o,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=Nt.get(e.strings);return void 0===t&&Nt.set(e.strings,t=new W(e)),t}k(e){Ve(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let r,o=0;for(const s of e)o===t.length?t.push(r=new n(this.O(j()),this.O(j()),this,this.options)):r=t[o],r._$AI(s),o++;o<t.length&&(this._$AR(r&&r._$AB.nextSibling,o),t.length=o)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(false,true,t);e!==this._$AB;){const r=zt(e).nextSibling;zt(e).remove(),e=r}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}};var M=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,o,s){this.type=1,this._$AH=c,this._$AN=void 0,this.element=e,this.name=t,this._$AM=o,this.options=s,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=c}_$AI(e,t=this,r,o){const s=this.strings;let i=false;if(void 0===s)e=L(this,e,t,0),i=!B(e)||e!==this._$AH&&e!==R,i&&(this._$AH=e);else{const u=e;let l,d;for(e=s[0],l=0;l<s.length-1;l++)d=L(this,u[r+l],t,l),d===R&&(d=this._$AH[l]),i||=!B(d)||d!==this._$AH[l],d===c?e=c:e!==c&&(e+=(d??"")+s[l+1]),this._$AH[l]=d}i&&!o&&this.j(e)}j(e){e===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}};var qe=class extends M{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===c?void 0:e}};var Ne=class extends M{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==c)}};var De=class extends M{constructor(e,t,r,o,s){super(e,t,r,o,s),this.type=5}_$AI(e,t=this){if((e=L(this,e,t,0)??c)===R)return;const r=this._$AH,o=e===c&&r!==c||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,s=e!==c&&(r===c||o);o&&this.element.removeEventListener(this.name,this,r),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}};var Ie=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){L(this,e)}};var Dn=Fe.litHtmlPolyfillSupport;Dn?.(W,Z),(Fe.litHtmlVersions??=[]).push("3.3.3");var jt=(n,e,t)=>{const r=t?.renderBefore??e;let o=r._$litPart$;if(void 0===o){const s=t?.renderBefore??null;r._$litPart$=o=new Z(e.insertBefore(j(),s),s,void 0,t??{})}return o._$AI(n),o};var Be=globalThis;var _=class extends ${constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=jt(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return R}};_._$litElement$=true,_["finalized"]=true,Be.litElementHydrateSupport?.({LitElement:_});var In=Be.litElementPolyfillSupport;In?.({LitElement:_});(Be.litElementVersions??=[]).push("4.2.2");var T=class extends Event{constructor(e,t,r,o){super("context-request",{bubbles:true,composed:true}),this.context=e,this.contextTarget=t,this.callback=r,this.subscribe=o??false}};function O(n){return n}var w=class{constructor(e,t,r,o){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(s,i)=>{this.unsubscribe&&(this.unsubscribe!==i&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=s,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(s,i)),this.unsubscribe=i},this.host=e,void 0!==t.context){const s=t;this.context=s.context,this.callback=s.callback,this.subscribe=s.subscribe??false}else this.context=t,this.callback=r,this.subscribe=o??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new T(this.context,this.host,this.t,this.subscribe))}};var Bt=ze`
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
    animation: hydronicus-card-enter 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
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
  .eyebrow { margin-block-end: 0.12rem; color: color-mix(in srgb, var(--_hy-state) 78%, var(--_hy-text)); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
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
  .badge.dry-run, .state.proposed { color: var(--_hy-warning); }
  .badge.mixed, .badge.live, .state.blocked, .state.mismatch { color: var(--_hy-danger); }
  .badge.mixed, .badge.live { background: color-mix(in srgb, var(--_hy-danger) 10%, transparent); }
  .phase.off { color: var(--_hy-text-muted); }
  .badge.active, .state.active, .state.ready { color: var(--_hy-success); }
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
  .shutdown { position: relative; overflow: hidden; color: var(--_hy-danger); touch-action: none; user-select: none; -webkit-user-select: none; }
  .shutdown.quiet { color: var(--_hy-text-muted); }
  .shutdown.quiet:hover, .shutdown.quiet:focus-visible, .shutdown.quiet.is-holding { color: var(--_hy-danger); }
  .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--_hy-danger) 18%, transparent); transform: scaleX(0); transform-origin: var(--_hy-inline-start); }
  .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
  .button-label { position: relative; z-index: 1; }
  .hold-progress { flex-basis: 100%; text-align: end; font-size: 0.7rem; color: var(--_hy-danger); }
  .alert, .error, .boundary, .notice { margin-block-start: 0.9rem; border: 1px solid var(--_hy-line); border-radius: var(--_hy-radius-inner); background: var(--_hy-surface-raised); padding: 0.68rem 0.75rem; }
  .alert, .notice, .action-error { position: relative; overflow: hidden; padding-inline-start: 0.9rem; }
  .alert::before, .notice::before, .action-error::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--_hy-warning); }
  .alert.error::before, .action-error::before { background: var(--_hy-danger); }
  .action-error { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-block-start: 0.9rem; border: 1px solid color-mix(in srgb, var(--_hy-danger) 40%, var(--_hy-line)); border-radius: var(--_hy-radius-inner); padding-block: 0.4rem; padding-inline-end: 0.4rem; color: var(--_hy-danger); font-size: 0.85rem; }
  .action-error button { min-block-size: 2.2rem; color: inherit; }
  .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
  .boundary-orb { display: grid; place-items: center; inline-size: 1.75rem; block-size: 1.75rem; border-radius: var(--_hy-radius-inner); background: color-mix(in srgb, var(--_hy-state) 14%, transparent); color: var(--_hy-state); }
  .boundary-orb::before { content: ""; inline-size: 0.55rem; block-size: 0.55rem; border: 2px solid currentColor; border-radius: 50%; }
  .boundary-copy { min-inline-size: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
  .boundary-copy strong { font-size: 0.82rem; font-weight: 600; }
  section { margin-block-start: 1.05rem; }
  .section-head { justify-content: space-between; margin-block-end: 0.5rem; }
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
  .diagnostic-chip.warning { color: var(--_hy-warning); border-color: color-mix(in srgb, var(--_hy-warning) 30%, var(--_hy-line)); }
  .diagnostic-chip.danger { color: var(--_hy-danger); border-color: color-mix(in srgb, var(--_hy-danger) 30%, var(--_hy-line)); }
  .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-block-start: 0.38rem; color: color-mix(in srgb, var(--_hy-warning) 80%, var(--_hy-text-muted)); }
  .hvac-modes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-block-start: 0.62rem; padding: 0.2rem; border: var(--_hy-control-border); border-radius: var(--_hy-radius-control); background: var(--_hy-control-surface); box-shadow: var(--_hy-control-shadow); }
  .hvac-mode { flex: 1 1 auto; min-block-size: 2.2rem; padding-inline: 0.4rem; border: 1px solid transparent; border-radius: max(0px, calc(var(--_hy-radius-control) - 0.2rem)); background: transparent; box-shadow: none; font-size: 0.8rem; white-space: nowrap; }
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
  .path[data-flowing="true"] .path-heading::before { background: var(--_hy-state); animation: hydronicus-pulse 2.4s ease-out infinite; }
  .path[data-status="blocked"] .path-heading::before { background: var(--_hy-danger); }
  .path-track { display: flex; align-items: stretch; margin-block-start: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding-block: 0.08rem 0.25rem; padding-inline: 0.03rem; scroll-snap-type: inline proximity; scrollbar-width: thin; }
  .path-step { display: contents; }
  .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-inline-size: 0; border: 1px solid var(--_hy-line); border-radius: calc(var(--_hy-radius-inner) * 0.75); padding: 0.48rem 0.52rem; font-size: 0.76rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, background-color 220ms ease; }
  .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--_hy-state) 34%, var(--_hy-line)); background: color-mix(in srgb, var(--_hy-state) 8%, transparent); }
  .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--_hy-danger) 36%, var(--_hy-line)); }
  .node-kind { color: var(--_hy-text-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .node-name { margin-block-start: 0.18rem; font-weight: 600; line-height: 1.25; }
  .node-state { display: flex; align-items: center; gap: 0.28rem; margin-block-start: 0.3rem; color: var(--_hy-text-muted); font-size: 0.68rem; }
  .node-state::before { content: ""; inline-size: 0.3rem; block-size: 0.3rem; border-radius: 50%; background: currentColor; }
  .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--_hy-state) 78%, var(--_hy-text)); }
  .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-inline-size: 1.2rem; align-self: center; block-size: 2px; margin-inline: 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--_hy-text-muted) 24%, transparent); }
  :host(:dir(rtl)) .flow-link { transform: scaleX(-1); }
  .flow-link::before { content: ""; position: absolute; inset-inline-end: 0; inset-block-start: 50%; inline-size: 0.34rem; block-size: 0.34rem; border-block-start: 1px solid var(--_hy-text-muted); border-inline-end: 1px solid var(--_hy-text-muted); transform: translateY(-50%) rotate(45deg); }
  .flow-link::after { content: ""; position: absolute; inset-block: -1px; inset-inline-start: 0; inline-size: 58%; background: linear-gradient(90deg, transparent, var(--_hy-state), transparent); opacity: 0; transform: translateX(-120%); }
  .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--_hy-state) 24%, transparent); }
  .path[data-flowing="true"] .flow-link::before { border-color: var(--_hy-state); }
  .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--_hy-flow-duration) linear infinite; }
  .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--_hy-danger) 30%, transparent); }
  .path-problem { margin-block-start: 0.5rem; color: var(--_hy-danger); }
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
    ha-card, ha-card::before, .plant-mark::before, .status-dot, .path-heading::before, .path[data-flowing="true"] .flow-link::after, details[open] .operation, .loading-mark, .skeleton { animation: none !important; }
    button, select, .zone, .node { transition-duration: 0.01ms !important; }
    .path[data-flowing="true"] .flow-link::after { opacity: 0.65; transform: translateX(40%); }
    .shutdown.is-holding::after { animation: none; transform: scaleX(1); }
  }

  @keyframes hydronicus-card-enter {
    from { opacity: 0; transform: translateY(8px) scale(0.992); }
    to { opacity: 1; transform: translateY(0) scale(1); }
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
`;var Vn=O("hassConnection");var jn=O("hassApi");var Bn=O("hassConfig");var Wn=O("hassInternationalization");var U=class extends _{static properties={preview:{type:Boolean},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_plant:{state:true},_actionError:{state:true}};static styles=Bt;_hass;_callService;_fromContext=new Set;_release;_followed;constructor(){super();this.preview=false;this._connection=void 0;this._unit=C;this._locale=void 0;this._localize=void 0;this._plant=H;this._actionError=null;new w(this,{context:Vn,subscribe:true,callback:e=>{this._fromContext.add("connection");this._connection=e?.connection}});new w(this,{context:jn,subscribe:true,callback:e=>{this._fromContext.add("api");this._callService=e?.callService}});new w(this,{context:Bn,subscribe:true,callback:e=>{this._fromContext.add("config");this._unit=fe(e?.config?.unit_system)}});new w(this,{context:Wn,subscribe:true,callback:e=>{this._fromContext.add("i18n");this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}})}set hass(e){this._hass=e;if(!this._fromContext.has("connection"))this._connection=e?.connection;if(!this._fromContext.has("api"))this._callService=e?(...t)=>e.callService(...t):void 0;if(!this._fromContext.has("config"))this._unit=fe(e?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}}get hass(){return this._hass}resetPlant(){this._plant=H;this._actionError=null}connectedCallback(){super.connectedCallback();this._follow()}disconnectedCallback(){this._unfollow();super.disconnectedCallback()}updated(e){super.updated(e);this._syncSelectValues();if(!this.isConnected)return;this._follow();if(this._connection&&(e.has("_connection")||this.preview))void v.load(this._connection)}_follow(){const e=this._connection;const t=this.plantId||void 0;const r=this._followed;if(r&&r.connection===e&&r.plantId===t)return;this._unfollow();if(!e||!t)return;this._followed={connection:e,plantId:t};this._release=z.subscribe(e,t,o=>{this._plant=o;this.plantStateChanged?.(o)})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._plant=H;this.plantStateChanged?.(H)}_syncSelectValues(){for(const e of this.renderRoot.querySelectorAll("select[data-value]")){const t=e.dataset.value??"";if(e.value!==t)e.value=t}}get renderContext(){return{unit:this._unit,locale:this._locale,localize:this._localize,moreInfo:e=>this.moreInfo(e),call:e=>this.call(e)}}moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:e}}))}call(e){const t=this._callService;if(!e||!t)return;t(e.domain,e.service,e.data,void 0,false).then(()=>{this._actionError=null},r=>{this._actionError=D(r,"The Home Assistant action failed.");this.requestUpdate()})}dismissActionError=()=>{this._actionError=null}};function Wt(n,e,t,r){const o=n.unit;if(e===null){return a`<div class=${r}><span class="metric-value">--</span><span class="metric-label">${t}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${r}><span class="metric-value">${ye(e,o,n.locale)}</span><span class="metric-unit">${o}</span><span class="metric-label">${t}</span></div>`}function Zt(n,e,t){const r=mt(e,t,n.unit);if(r!==null)n.call(ot(e,r))}function Zn(n,e,t){if(t===e.thermostat.hvac_mode)return;n.call(it(e,t))}function Yn(n,e,t){n.call(st(e,t.target.value))}function se(n,e,t){const r=e.thermostat;const o=r.kind==="hydronicus";const s=e.cooling.demand?"cooling":e.demand?"heating":"none";const i=s!=="none";const u=r.hvac_mode==="off";const{unit:l,locale:d,localize:p}=n;const h=y(ge(l),d,l===C?1:0);const m=r.control_entity_id;const g=Boolean(m)&&r.target_temperature!==null;const k=pt(e);const Ye=_e(e);const pe=r.hvac_mode?ve(p,r.hvac_mode):null;const sn=u&&!e.blocked?pe??"Off":f(e.phase);const Ge=i?`${s==="cooling"?"Cooling":"Heating"} demand active`:u?"Thermostat off":"No demand";const me=`zone-${e.id}`;const Ke=m?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>n.moreInfo(m)}>${e.name}</button>`:e.name;const an=t.headingLevel===2?a`<h2 class="zone-title" id=${me}>${Ke}</h2>`:a`<h4 class="zone-title" id=${me}>${Ke}</h4>`;return a`<article class="zone" data-phase=${e.phase} data-hvac-mode=${r.hvac_mode??"unknown"} data-demand=${String(i)} data-demand-kind=${s} data-blocked=${String(e.blocked)} aria-labelledby=${me}>
    <div class="row"><div>${an}<p class="meta zone-owner">${o?"Hydronicus thermostat":`External thermostat \xB7 read-only${pe?` \xB7 ${pe}`:""}`}</p></div><span class=${`phase${e.blocked?" state blocked":""}${u?" off":""}`}>${sn}</span></div>
    <div class="temperature-panel">
      ${Wt(n,r.current_temperature,"Current","metric")}
      ${Wt(n,r.target_temperature,"Target","metric target")}
    </div>
    <p class="meta zone-note" dir="auto">${o?Ge:`${Ge} \xB7 ${r.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Room diagnostics">
      <li class="diagnostic-chip" dir="auto">${y(e.sensor_status.usable,d,0)} sensor${e.sensor_status.usable===1?"":"s"} ready</li>
      ${e.sensor_status.optional_excluded?a`<li class="diagnostic-chip warning" dir="auto">${y(e.sensor_status.optional_excluded,d,0)} optional excluded</li>`:c}
      ${e.sensor_status.required_blocking?a`<li class="diagnostic-chip danger" dir="auto">${y(e.sensor_status.required_blocking,d,0)} required blocked</li>`:c}
      ${e.cooling.dew_point===null?c:a`<li class="diagnostic-chip" dir="auto">Dew point ${ye(e.cooling.dew_point,l,d)} ${l}</li>`}
      ${e.cooling.condensation_margin===null?c:a`<li class="diagnostic-chip ${e.cooling.blocked?"danger":""}" dir="auto">Margin ${Qe(e.cooling.condensation_margin,l,d)} ${l}</li>`}
    </ul>
    ${r.preset&&r.preset!=="none"?a`<p class="meta zone-note" dir="auto">Preset: ${f(r.preset)}</p>`:c}
    ${e.blocked_reason?a`<p class="meta zone-note" dir="auto">${e.blocked_reason}</p>`:c}
    ${e.coupling_group_ids.length?a`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>`:c}
    ${o?a`${Ye.length?a`<div class="hvac-modes" role="group" aria-label=${`${e.name} HVAC mode`}>${Ye.map(x=>a`<button type="button" class="hvac-mode" data-mode=${x} aria-pressed=${String(x===r.hvac_mode)} ?disabled=${!m} @click=${()=>Zn(n,e,x)}>${ve(p,x)}</button>`)}</div>`:c}
          <div class="zone-actions">
            <button type="button" dir="ltr" ?disabled=${!g} aria-label=${`Decrease ${e.name} target by ${h} ${l}`} @click=${()=>Zt(n,e,-1)}>−${h}</button>
            <button type="button" dir="ltr" ?disabled=${!g} aria-label=${`Increase ${e.name} target by ${h} ${l}`} @click=${()=>Zt(n,e,1)}>+${h}</button>
            ${k.length?a`<select class="preset" data-value=${r.preset??"none"} aria-label=${`${e.name} preset`} ?disabled=${!m} @change=${x=>Yn(n,e,x)}>${["none",...k].map(x=>a`<option value=${x}>${f(x)}</option>`)}</select>`:c}
          </div>`:a`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`}var We=["auto","idle","heating","cooling"];function Gn(n,e){const t=e.plant;const r=`Mode ${N(n.localize,"select.requested_mode",t.requested_mode)}`;if(t.requested_mode==="auto"||t.requested_mode===t.active_mode)return r;return`${r} \xB7 now ${N(n.localize,"sensor.operating_mode",t.active_mode)}`}function Yt(n,e,t){const r=e.plant;const o=r.execution_boundary;const s=e.controls.requested_mode;const i=We.includes(r.requested_mode)?We:[...We,r.requested_mode];const u=ut(e);const l=d=>n.call(at(e,d.target.value));return a`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${s?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>n.moreInfo(s)}>${r.name}</button>`:r.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${N(n.localize,"sensor.controller_status",r.status)}</span>
            <span class="meta mode-detail">${Gn(n,e)}</span>
          </div>
          ${u===null?c:a`<p class="meta source-line" dir="auto"><strong>Source</strong> ${u}</p>`}
          <p class="meta" dir="auto">${r.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${dt(o)}"><span class="visually-hidden">Execution boundary: </span>${xe(o)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${r.requested_mode} ?disabled=${!s} @change=${l}>
          ${i.map(d=>a`<option value=${d}>${N(n.localize,"select.requested_mode",d)}</option>`)}
        </select></label>
        ${t}
      </div>
    </header>`}function Gt(n){return a`<div class="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${n.plant.execution_boundary.message||`${xe(n.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`}function Kt(n,e){const t=tt(e);if(!t.length)return c;return a`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${y(t.length,n.locale,0)}</span></div>${t.slice(0,3).map(r=>{const o=r.severity==="error"||r.severity==="critical";return a`<p class="alert ${o?"error":""}" data-severity=${r.severity} dir="auto"><strong>${ht(r)}</strong><span> · ${r.message}</span></p>`})}</section>`}function Xt(n,e){return a`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${y(e.zones.length,n.locale,0)} visible</span></div><div class="zone-grid">${e.zones.length?e.zones.map(t=>se(n,t,{headingLevel:4})):a`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`}function Jt(n){if(!n.delivery_paths.length)return c;return a`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${n.delivery_paths.map(e=>a`<article class="path" data-status=${e.status} data-flowing=${String(be(e.status))}>
    <div class="path-head"><div class="path-heading"><strong>${n.zones.find(t=>t.id===e.zone_id)?.name??e.zone_id}</strong></div><div class="status-line"><span class="state ${e.status}">${f(e.status)}</span>${e.coupled?a`<span class="meta">shares equipment</span>`:c}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${e.nodes.map((t,r)=>a`<li class="path-step">${r?a`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" data-kind=${t.kind} data-state=${t.state} data-flowing=${String(be(t.state))}><span class="node-kind">${$e(t.kind)}</span><span class="node-name">${t.name}</span><span class="node-state">${f(t.state)}</span></span></li>`)}</ol>
    ${e.problem?a`<p class="meta path-problem" dir="auto">${e.problem}</p>`:c}
  </article>`)}</div></section>`}function Qt(n){if(!n.actuators.length)return c;return a`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${n.actuators.map(e=>a`<article class="actuator" data-state=${e.state}><div class="row"><strong>${e.name}</strong><span class="state actuator-state ${e.state}">${f(e.state)}</span></div><p class="meta" dir="auto">${f(e.kind)} · ${e.reason??"No additional explanation."}</p>${e.active_consumers.length?a`<ul class="consumer-list" aria-label="Loops using this equipment">${e.active_consumers.map(t=>a`<li class="consumer-chip" title=${t.id}><strong>${t.name}</strong></li>`)}</ul>`:a`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}function en(n){return a`<section><details><summary>Controller explanations</summary>${n.explanations.map(e=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${e.name??$e(e.scope)}</strong> · ${e.message}</p></div>`)}</details></section>`}function tn(n,e){const t=Object.values(e.execution.operations).flat();if(!t.length)return c;return a`<section><details open><summary>Latest operation outcomes (${y(t.length,n.locale,0)})</summary>${t.map(r=>{const o=String(r.result??"unknown");return a`<div class="operation" data-result=${o}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${ct(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}function nn(n){return`Retrying in ${Math.round(n/1e3)} s.`}function b(n,e,t,r,o){return a`<ha-card class="state-card" data-visual=${r==="alert"?"attention":"idle"}>
    <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">${n}</p><h2>${e}</h2></div></div>
    <p class=${r==="alert"?"notice error":"notice"} role=${r} dir="auto">${t}</p>
    ${o?a`<p class="meta" dir="auto">${o}</p>`:c}
  </ha-card>`}function Kn(n){return a`<ha-card class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${n?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
  </ha-card>`}function ie(n){return n.snapshotError?null:n.snapshot}function ae(n,e){if(e.snapshotError){return b(n,"Card update needed",e.snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const t=e.status;switch(t.kind){case"not_found":return b(n,"Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return b(n,"No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return b(n,"Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return b(n,"Connection needs attention",t.message,"alert",nn(t.delayMs));default:return Kn(t.kind==="reconnecting")}}function le(n){if(n.kind==="reconnecting"){return a`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(n.kind==="retrying"){return a`<p class="notice" role="status" dir="auto">${n.message} ${nn(n.delayMs)} The values below may be out of date.</p>`}return c}function ce(n,e){if(!n)return c;return a`<div class="action-error" role="alert"><span dir="auto">${n}</span><button type="button" @click=${e}>Dismiss</button></div>`}var Xn=1200;var Ze="Hydronicus Plant";var Jn=["rooms","paths","equipment"];function Qn(n,e){switch(n){case"header":return 4;case"alerts":{const t=Math.min(e.alerts.length,3);return t?1+t:0}case"rooms":return 1+Math.max(1,e.zones.length)*5;case"paths":return e.delivery_paths.length?1+e.delivery_paths.length*3:0;case"equipment":return e.actuators.length?1+e.actuators.length*2:0;case"explanations":return 1;case"operations":{const t=Object.values(e.execution.operations).flat().length;return t?1+t:0}}}var de=class extends U{static properties={_config:{state:true},_holdingShutdown:{state:true}};_holdTimer=null;constructor(){super();this._config=void 0;this._holdingShutdown=false}static async getConfigForm(){return kt()}static async getStubConfig(e){return $t(e)}setConfig(e){const t=Pe(e);if(t.plant!==this._config?.plant)this.resetPlant();this._config=t}get plantId(){return this._config?.plant}getCardSize(){const e=this._plant.snapshot;const t=Q(this._config);if(!e)return t.includes("header")?4:2;return Math.max(1,t.reduce((r,o)=>r+Qn(o,e),0))}getGridOptions(){const e=Q(this._config).some(t=>Jn.includes(t));return e?{columns:12,min_columns:6}:{columns:6,min_columns:4}}disconnectedCallback(){this._clearHold();super.disconnectedCallback()}plantStateChanged(e){if(!e.snapshot)this._clearHold()}render(){const e=this._config;if(!e||!e.plant){return b(Ze,Ze,"Select a Hydronicus Plant in the card editor.","status")}const t=this._plant;const r=ie(t);if(!r)return ae(Ze,t);const o=this.renderContext;const s=Q(e);const i=a`${le(t.status)}${ce(this._actionError,this.dismissActionError)}`;return a`<ha-card class=${e.density??"comfortable"} data-visual=${nt(r)}>
      ${s.includes("header")?c:i}
      ${s.map(u=>this._renderSection(u,o,r,i))}
    </ha-card>`}_renderSection(e,t,r,o){switch(e){case"header":return a`${Yt(t,r,this._renderShutdown(r))}
          ${o}
          ${Gt(r)}`;case"alerts":return Kt(t,r);case"rooms":return Xt(t,r);case"paths":return Jt(r);case"equipment":return Qt(r);case"explanations":return en(r);case"operations":return tn(t,r)}}_renderShutdown(e){const t=!e.controls.safe_shutdown;const r=e.plant.execution_boundary.dry_run;return a`<button type="button" class=${`shutdown${r?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${t} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_startHold(){if(!this._plant.snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;const e=this._plant.snapshot;if(e)this.call(lt(e))},Xn)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=e=>{if(e.button!==void 0&&e.button>0)return;this._startHold()};_keyHoldStart=e=>{if(e.key!=="Enter"&&e.key!==" ")return;e.preventDefault();if(!e.repeat)this._startHold()};_keyHoldEnd=e=>{if(e.key==="Enter"||e.key===" ")this._clearHold()};_preventContextMenu=e=>{e.preventDefault()}};var q="Hydronicus Room";var ue=class extends U{static properties={_config:{state:true}};constructor(){super();this._config=void 0}static getConfigElement(){return document.createElement(J)}static async getStubConfig(e){return wt(e)}setConfig(e){const t=ee(e);if(t.plant!==this._config?.plant)this.resetPlant();else if(t.room!==this._config?.room)this._actionError=null;this._config=t}get plantId(){return this._config?.room?this._config.plant:void 0}getCardSize(){return 5}getGridOptions(){return{columns:6,min_columns:4}}render(){const e=this._config;if(!e||!e.plant){return b(q,q,"Select a Hydronicus Plant and a Room in the card editor.","status")}if(!e.room){return b(q,q,"Select a Room in the card editor.","status")}const t=this._plant;const r=ie(t);if(!r)return ae(q,t);const o=r.zones.find(s=>s.id===e.room);if(!o){return b(q,"Room not found","This Room is not in the Plant, or you do not have access to it. Choose another Room in the card editor.","alert")}return a`<ha-card class="room-card ${e.density??"comfortable"}" data-visual=${rt(o)}>
      ${le(t.status)}
      ${ce(this._actionError,this.dismissActionError)}
      ${se(this.renderContext,o,{headingLevel:2})}
    </ha-card>`}};var he=class extends _{static properties={hass:{attribute:false},_config:{state:true},_plants:{state:true},_rooms:{state:true}};_release;_followed;_directoryConnection;constructor(){super();this.hass=void 0;this._config=void 0;this._plants=v.known;this._rooms=[]}setConfig(e){ee(e);this._config=e}connectedCallback(){super.connectedCallback();this.requestUpdate()}disconnectedCallback(){this._unfollow();this._directoryConnection=void 0;super.disconnectedCallback()}updated(e){super.updated(e);if(!this.isConnected)return;const t=this.hass?.connection;if(t&&t!==this._directoryConnection){this._directoryConnection=t;void v.load(t).then(r=>{this._plants=r})}this._follow(t,this._config?.plant||void 0)}_follow(e,t){const r=this._followed;if(r?.connection===e&&r?.plantId===t)return;this._unfollow();if(!e||!t)return;this._followed={connection:e,plantId:t};this._release=z.subscribe(e,t,o=>{if(o.snapshot)this._rooms=o.snapshot.zones.map(s=>({id:s.id,name:s.name}))})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._rooms=[]}render(){return a`<ha-form
      .hass=${this.hass}
      .data=${this._config??{}}
      .schema=${Ct(this._plants,this._rooms)}
      .computeLabel=${Re}
      .computeHelper=${Te}
      @value-changed=${this._valueChanged}
    ></ha-form>`}_valueChanged(e){e.stopPropagation();const t={...e.detail.value};if(t.plant!==this._config?.plant)t.room="";this._config=t;this.dispatchEvent(new CustomEvent("config-changed",{bubbles:true,composed:true,detail:{config:t}}))}};var er=[[K,de],[X,ue],[J,he]];function rn(n){for(const[e,t]of er){if(!n.get(e))n.define(e,t)}}var on=window.customElements;rn(on);void on.whenDefined("home-assistant").then(()=>{rn(window.customElements)});var tr=[{type:K,name:"Hydronicus Plant",description:"Topology-driven Hydronicus Plant status and controls."},{type:X,name:"Hydronicus Room",description:"One Room of a Hydronicus Plant, with its thermostat and controls."}];window.customCards=window.customCards??[];for(const n of tr){if(window.customCards.some(e=>e.type===n.type))continue;window.customCards.push({...n,version:"0.1.0-rc.6",preview:true,documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
