var U=globalThis;var N=U.ShadowRoot&&(void 0===U.ShadyCSS||U.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var j=Symbol();var te=new WeakMap;var A=class{constructor(e,t,r){if(this._$cssResult$=true,r!==j)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(N&&void 0===e){const r=void 0!==t&&1===t.length;r&&(e=te.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&te.set(t,e))}return e}toString(){return this.cssText}};var re=s=>new A("string"==typeof s?s:s+"",void 0,j);var R=(s,...e)=>{const t=1===s.length?s[0]:e.reduce((r,n,o)=>r+(a=>{if(true===a._$cssResult$)return a.cssText;if("number"==typeof a)return a;throw Error("Value passed to 'css' function must be a 'css' function result: "+a+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+s[o+1],s[0]);return new A(t,s,j)};var se=(s,e)=>{if(N)s.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const t of e){const r=document.createElement("style"),n=U.litNonce;void 0!==n&&r.setAttribute("nonce",n),r.textContent=t.cssText,s.appendChild(r)}};var D=N?s=>s:s=>s instanceof CSSStyleSheet?(e=>{let t="";for(const r of e.cssRules)t+=r.cssText;return re(t)})(s):s;var{is:Ee,defineProperty:Pe,getOwnPropertyDescriptor:He,getOwnPropertyNames:Te,getOwnPropertySymbols:Oe,getPrototypeOf:Me}=Object;var z=globalThis;var ne=z.trustedTypes;var Ue=ne?ne.emptyScript:"";var Ne=z.reactiveElementPolyfillSupport;var C=(s,e)=>s;var q={toAttribute(s,e){switch(e){case Boolean:s=s?Ue:null;break;case Object:case Array:s=null==s?s:JSON.stringify(s)}return s},fromAttribute(s,e){let t=s;switch(e){case Boolean:t=null!==s;break;case Number:t=null===s?null:Number(s);break;case Object:case Array:try{t=JSON.parse(s)}catch(r){t=null}}return t}};var ae=(s,e)=>!Ee(s,e);var oe={attribute:true,type:String,converter:q,reflect:false,useDefault:false,hasChanged:ae};Symbol.metadata??=Symbol("metadata"),z.litPropertyMetadata??=new WeakMap;var b=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=oe){if(t.state&&(t.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=true),this.elementProperties.set(e,t),!t.noAccessor){const r=Symbol(),n=this.getPropertyDescriptor(e,r,t);void 0!==n&&Pe(this.prototype,e,n)}}static getPropertyDescriptor(e,t,r){const{get:n,set:o}=He(this.prototype,e)??{get(){return this[t]},set(a){this[t]=a}};return{get:n,set(a){const h=n?.call(this);o?.call(this,a),this.requestUpdate(e,h,r)},configurable:true,enumerable:true}}static getPropertyOptions(e){return this.elementProperties.get(e)??oe}static _$Ei(){if(this.hasOwnProperty(C("elementProperties")))return;const e=Me(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(C("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(C("properties"))){const t=this.properties,r=[...Te(t),...Oe(t)];for(const n of r)this.createProperty(n,t[n])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[r,n]of t)this.elementProperties.set(r,n)}this._$Eh=new Map;for(const[t,r]of this.elementProperties){const n=this._$Eu(t,r);void 0!==n&&this._$Eh.set(n,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const r=new Set(e.flat(1/0).reverse());for(const n of r)t.unshift(D(n))}else void 0!==e&&t.push(D(e));return t}static _$Eu(e,t){const r=t.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return se(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){const r=this.constructor.elementProperties.get(e),n=this.constructor._$Eu(e,r);if(void 0!==n&&true===r.reflect){const o=(void 0!==r.converter?.toAttribute?r.converter:q).toAttribute(t,r.type);this._$Em=e,null==o?this.removeAttribute(n):this.setAttribute(n,o),this._$Em=null}}_$AK(e,t){const r=this.constructor,n=r._$Eh.get(e);if(void 0!==n&&this._$Em!==n){const o=r.getPropertyOptions(n),a="function"==typeof o.converter?{fromAttribute:o.converter}:void 0!==o.converter?.fromAttribute?o.converter:q;this._$Em=n;const h=a.fromAttribute(t,o.type);this[n]=h??this._$Ej?.get(n)??h,this._$Em=null}}requestUpdate(e,t,r,n=false,o){if(void 0!==e){const a=this.constructor;if(false===n&&(o=this[e]),r??=a.getPropertyOptions(e),!((r.hasChanged??ae)(o,t)||r.useDefault&&r.reflect&&o===this._$Ej?.get(e)&&!this.hasAttribute(a._$Eu(e,r))))return;this.C(e,t,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:n,wrapped:o},a){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,a??t??this[e]),true!==o||void 0!==a)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),true===n&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(t){Promise.reject(t)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[n,o]of this._$Ep)this[n]=o;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[n,o]of r){const{wrapped:a}=o,h=this[n];true!==a||this._$AL.has(n)||void 0===h||this.C(n,void 0,o,h)}}let e=false;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=false,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return true}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[C("elementProperties")]=new Map,b[C("finalized")]=new Map,Ne?.({ReactiveElement:b}),(z.reactiveElementVersions??=[]).push("2.1.2");var X=globalThis;var ie=s=>s;var L=X.trustedTypes;var le=L?L.createPolicy("lit-html",{createHTML:s=>s}):void 0;var me="$lit$";var v=`lit$${Math.random().toFixed(9).slice(2)}$`;var ge="?"+v;var Re=`<${ge}>`;var x=document;var P=()=>x.createComment("");var H=s=>null===s||"object"!=typeof s&&"function"!=typeof s;var G=Array.isArray;var ze=s=>G(s)||"function"==typeof s?.[Symbol.iterator];var Z="[ 	\n\f\r]";var E=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var de=/-->/g;var ce=/>/g;var _=RegExp(`>|${Z}(?:([^\\s"'>=/]+)(${Z}*=${Z}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var he=/'/g;var pe=/"/g;var be=/^(?:script|style|textarea|title)$/i;var K=s=>(e,...t)=>({_$litType$:s,strings:e,values:t});var i=K(1);var Xe=K(2);var Ge=K(3);var w=Symbol.for("lit-noChange");var d=Symbol.for("lit-nothing");var ue=new WeakMap;var $=x.createTreeWalker(x,129);function fe(s,e){if(!G(s)||!s.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==le?le.createHTML(e):e}var Le=(s,e)=>{const t=s.length-1,r=[];let n,o=2===e?"<svg>":3===e?"<math>":"",a=E;for(let h=0;h<t;h++){const l=s[h];let p,m,c=-1,g=0;for(;g<l.length&&(a.lastIndex=g,m=a.exec(l),null!==m);)g=a.lastIndex,a===E?"!--"===m[1]?a=de:void 0!==m[1]?a=ce:void 0!==m[2]?(be.test(m[2])&&(n=RegExp("</"+m[2],"g")),a=_):void 0!==m[3]&&(a=_):a===_?">"===m[0]?(a=n??E,c=-1):void 0===m[1]?c=-2:(c=a.lastIndex-m[2].length,p=m[1],a=void 0===m[3]?_:'"'===m[3]?pe:he):a===pe||a===he?a=_:a===de||a===ce?a=E:(a=_,n=void 0);const y=a===_&&s[h+1].startsWith("/>")?" ":"";o+=a===E?l+Re:c>=0?(r.push(p),l.slice(0,c)+me+l.slice(c)+v+y):l+v+(-2===c?h:y)}return[fe(s,o+(s[t]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),r]};var T=class s{constructor({strings:e,_$litType$:t},r){let n;this.parts=[];let o=0,a=0;const h=e.length-1,l=this.parts,[p,m]=Le(e,t);if(this.el=s.createElement(p,r),$.currentNode=this.el.content,2===t||3===t){const c=this.el.content.firstChild;c.replaceWith(...c.childNodes)}for(;null!==(n=$.nextNode())&&l.length<h;){if(1===n.nodeType){if(n.hasAttributes())for(const c of n.getAttributeNames())if(c.endsWith(me)){const g=m[a++],y=n.getAttribute(c).split(v),M=/([.?@])?(.*)/.exec(g);l.push({type:1,index:o,name:M[2],strings:y,ctor:"."===M[1]?I:"?"===M[1]?V:"@"===M[1]?B:S}),n.removeAttribute(c)}else c.startsWith(v)&&(l.push({type:6,index:o}),n.removeAttribute(c));if(be.test(n.tagName)){const c=n.textContent.split(v),g=c.length-1;if(g>0){n.textContent=L?L.emptyScript:"";for(let y=0;y<g;y++)n.append(c[y],P()),$.nextNode(),l.push({type:2,index:++o});n.append(c[g],P())}}}else if(8===n.nodeType)if(n.data===ge)l.push({type:2,index:o});else{let c=-1;for(;-1!==(c=n.data.indexOf(v,c+1));)l.push({type:7,index:o}),c+=v.length-1}o++}}static createElement(e,t){const r=x.createElement("template");return r.innerHTML=e,r}};function k(s,e,t=s,r){if(e===w)return e;let n=void 0!==r?t._$Co?.[r]:t._$Cl;const o=H(e)?void 0:e._$litDirective$;return n?.constructor!==o&&(n?._$AO?.(false),void 0===o?n=void 0:(n=new o(s),n._$AT(s,t,r)),void 0!==r?(t._$Co??=[])[r]=n:t._$Cl=n),void 0!==n&&(e=k(s,n._$AS(s,e.values),n,r)),e}var F=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:r}=this._$AD,n=(e?.creationScope??x).importNode(t,true);$.currentNode=n;let o=$.nextNode(),a=0,h=0,l=r[0];for(;void 0!==l;){if(a===l.index){let p;2===l.type?p=new O(o,o.nextSibling,this,e):1===l.type?p=new l.ctor(o,l.name,l.strings,this,e):6===l.type&&(p=new W(o,this,e)),this._$AV.push(p),l=r[++h]}a!==l?.index&&(o=$.nextNode(),a++)}return $.currentNode=x,n}p(e){let t=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}};var O=class s{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,n){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=n,this._$Cv=n?.isConnected??true}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=k(this,e,t),H(e)?e===d||null==e||""===e?(this._$AH!==d&&this._$AR(),this._$AH=d):e!==this._$AH&&e!==w&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):ze(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==d&&H(this._$AH)?this._$AA.nextSibling.data=e:this.T(x.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:r}=e,n="number"==typeof r?this._$AC(e):(void 0===r.el&&(r.el=T.createElement(fe(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===n)this._$AH.p(t);else{const o=new F(n,this),a=o.u(this.options);o.p(t),this.T(a),this._$AH=o}}_$AC(e){let t=ue.get(e.strings);return void 0===t&&ue.set(e.strings,t=new T(e)),t}k(e){G(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let r,n=0;for(const o of e)n===t.length?t.push(r=new s(this.O(P()),this.O(P()),this,this.options)):r=t[n],r._$AI(o),n++;n<t.length&&(this._$AR(r&&r._$AB.nextSibling,n),t.length=n)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(false,true,t);e!==this._$AB;){const r=ie(e).nextSibling;ie(e).remove(),e=r}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}};var S=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,n,o){this.type=1,this._$AH=d,this._$AN=void 0,this.element=e,this.name=t,this._$AM=n,this.options=o,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=d}_$AI(e,t=this,r,n){const o=this.strings;let a=false;if(void 0===o)e=k(this,e,t,0),a=!H(e)||e!==this._$AH&&e!==w,a&&(this._$AH=e);else{const h=e;let l,p;for(e=o[0],l=0;l<o.length-1;l++)p=k(this,h[r+l],t,l),p===w&&(p=this._$AH[l]),a||=!H(p)||p!==this._$AH[l],p===d?e=d:e!==d&&(e+=(p??"")+o[l+1]),this._$AH[l]=p}a&&!n&&this.j(e)}j(e){e===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}};var I=class extends S{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===d?void 0:e}};var V=class extends S{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==d)}};var B=class extends S{constructor(e,t,r,n,o){super(e,t,r,n,o),this.type=5}_$AI(e,t=this){if((e=k(this,e,t,0)??d)===w)return;const r=this._$AH,n=e===d&&r!==d||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,o=e!==d&&(r===d||n);n&&this.element.removeEventListener(this.name,this,r),o&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}};var W=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){k(this,e)}};var je=X.litHtmlPolyfillSupport;je?.(T,O),(X.litHtmlVersions??=[]).push("3.3.3");var ye=(s,e,t)=>{const r=t?.renderBefore??e;let n=r._$litPart$;if(void 0===n){const o=t?.renderBefore??null;r._$litPart$=n=new O(e.insertBefore(P(),o),o,void 0,t??{})}return n._$AI(s),n};var Y=globalThis;var f=class extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=ye(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return w}};f._$litElement$=true,f["finalized"]=true,Y.litElementHydrateSupport?.({LitElement:f});var De=Y.litElementPolyfillSupport;De?.({LitElement:f});(Y.litElementVersions??=[]).push("4.2.2");var qe=2;var Ze=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function ve(s){if(!s||typeof s!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const e=s;if(e.schema_version!==qe){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(e.schema_version)}.`)}if(!e.plant||!Array.isArray(e.zones)||!Array.isArray(e.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return e}function _e(s){return[...s.alerts].sort((e,t)=>e.priority-t.priority||e.code.localeCompare(t.code)||e.scope.localeCompare(t.scope))}function $e(s){const e=s.plant.health.toLowerCase();const t=s.alerts.some(n=>n.severity==="critical"||n.severity==="error");if(s.safe_shutdown.active||t||["blocked","critical","error","failed","unhealthy"].includes(e)){return"attention"}const r=`${s.plant.active_mode} ${s.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function J(s){return Ze.has(s.toLowerCase())}function xe(s,e){if(s.thermostat.kind!=="hydronicus"||!s.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:s.thermostat.control_entity_id,temperature:e}}}function we(s,e){if(s.thermostat.kind!=="hydronicus"||!s.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:s.thermostat.control_entity_id,preset_mode:e}}}function ke(s,e){if(!s.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:s.controls.requested_mode,option:e}}}function Se(s){if(!s.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:s.controls.safe_shutdown}}}function Ae(s){const e=String(s.action??"operation").replaceAll("_"," ");const t=String(s.actuator_name??"actuator");const r=String(s.result??"");if(r==="proposed")return`Would ${e} ${t}`;if(r==="executed")return`Executed ${t} ${e}`;if(r==="suppressed")return`Suppressed ${t} ${e}`;return`${r||"Operation"}: ${t} ${e}`}function u(s){return s.replaceAll("_"," ")}function Ce(s,e){if(s.thermostat.target_temperature===null)return null;return Math.min(35,Math.max(5,Number((s.thermostat.target_temperature+e).toFixed(1))))}var Fe=["auto","idle","heating","cooling"];var Q=class extends f{static properties={hass:{attribute:false},_config:{state:true},_snapshot:{state:true},_error:{state:true},_reconnecting:{state:true},_holdingShutdown:{state:true}};static styles=R`
    :host {
      display: block;
      color: var(--primary-text-color, #1c1c1c);
      --hydronicus-border: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 13%, transparent);
      --hydronicus-muted: var(--secondary-text-color, #5f6368);
      --hydronicus-surface: var(--ha-card-background, var(--card-background-color, #fff));
      --hydronicus-danger: var(--error-color, #ba1a1a);
      --hydronicus-warning: var(--warning-color, #8a5a00);
      --hydronicus-accent: var(--primary-color, #03a9f4);
      --hydronicus-heating-color: #ff9b62;
      --hydronicus-cooling-color: #55c9f6;
      --hydronicus-idle-color: var(--primary-color, #7b9bb4);
      --hydronicus-attention-color: var(--error-color, #ef6a72);
      --hydronicus-glass-blur: 24px;
      --hydronicus-glass-opacity: 68%;
      --hydronicus-flow-duration: 2.2s;
      --hydronicus-ambient-duration: 16s;
      --hydronicus-state-color: var(--hydronicus-idle-color);
      --hydronicus-state-rgb: 123 155 180;
      font-variant-numeric: tabular-nums;
    }

    .card {
      box-sizing: border-box;
      container-type: inline-size;
      overflow: hidden;
      position: relative;
      isolation: isolate;
      border: 1px solid color-mix(in srgb, white 42%, var(--hydronicus-border));
      border-radius: var(--ha-card-border-radius, 22px);
      background: var(--hydronicus-surface);
      background: color-mix(in srgb, var(--hydronicus-surface) var(--hydronicus-glass-opacity), transparent);
      box-shadow:
        inset 0 1px 0 color-mix(in srgb, white 48%, transparent),
        inset 0 -1px 0 color-mix(in srgb, var(--primary-text-color, #1c1c1c) 5%, transparent),
        var(--ha-card-box-shadow, 0 20px 50px rgba(20, 35, 50, 0.12));
      -webkit-backdrop-filter: blur(var(--hydronicus-glass-blur)) saturate(145%);
      backdrop-filter: blur(var(--hydronicus-glass-blur)) saturate(145%);
      padding: 1.15rem;
      animation: hydronicus-card-enter 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
    }

    .card::before {
      content: "";
      position: absolute;
      z-index: -2;
      inset: -35%;
      pointer-events: none;
      background:
        radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent) 0, transparent 32%),
        radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--hydronicus-accent) 13%, transparent) 0, transparent 30%),
        radial-gradient(circle at 74% 92%, color-mix(in srgb, white 15%, transparent) 0, transparent 34%);
      opacity: 0.82;
      transform: translate3d(-2%, -1%, 0) scale(1.02);
      animation: hydronicus-ambient var(--hydronicus-ambient-duration) ease-in-out infinite alternate;
    }

    .card::after {
      content: "";
      position: absolute;
      z-index: -1;
      inset: 0;
      pointer-events: none;
      border-radius: inherit;
      background: linear-gradient(145deg, color-mix(in srgb, white 14%, transparent), transparent 34%, color-mix(in srgb, var(--hydronicus-state-color) 5%, transparent));
    }

    .card[data-visual="heating"] {
      --hydronicus-state-color: var(--hydronicus-heating-color);
      --hydronicus-state-rgb: 255 155 98;
    }

    .card[data-visual="cooling"] {
      --hydronicus-state-color: var(--hydronicus-cooling-color);
      --hydronicus-state-rgb: 85 201 246;
    }

    .card[data-visual="attention"] {
      --hydronicus-state-color: var(--hydronicus-attention-color);
      --hydronicus-state-rgb: 239 106 114;
    }

    .card.compact { padding: 0.8rem; }
    .header, .row, .path-head, .action-row, .section-head, .plant-heading, .status-line, .boundary-copy { display: flex; align-items: center; gap: 0.65rem; }
    .header { justify-content: space-between; align-items: flex-start; gap: 1.2rem; }
    .header-copy { min-width: 0; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: clamp(1.18rem, 3cqi, 1.5rem); font-weight: 650; letter-spacing: -0.025em; overflow-wrap: anywhere; }
    h2 { font-size: 0.92rem; font-weight: 650; letter-spacing: 0.01em; }
    h3 { font-size: 0.9rem; font-weight: 650; }
    .muted, .meta { color: var(--hydronicus-muted); font-size: 0.8rem; line-height: 1.45; }
    .eyebrow { margin-bottom: 0.12rem; color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); font-size: 0.64rem; font-weight: 750; letter-spacing: 0.13em; text-transform: uppercase; }
    .plant-heading { align-items: flex-start; }
    .plant-mark {
      position: relative;
      flex: 0 0 2.7rem;
      width: 2.7rem;
      height: 2.7rem;
      border: 1px solid color-mix(in srgb, white 38%, var(--hydronicus-border));
      border-radius: 1rem;
      background: linear-gradient(145deg, color-mix(in srgb, white 20%, transparent), color-mix(in srgb, var(--hydronicus-state-color) 13%, transparent));
      box-shadow: inset 0 1px 0 color-mix(in srgb, white 50%, transparent), 0 8px 22px color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
    }
    .plant-mark::before {
      content: "";
      position: absolute;
      inset: 0.58rem;
      border: 2px solid color-mix(in srgb, var(--hydronicus-state-color) 30%, transparent);
      border-top-color: var(--hydronicus-state-color);
      border-radius: 50%;
      animation: hydronicus-spin 3.8s linear infinite;
    }
    .plant-mark::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 50%;
      width: 0.42rem;
      height: 0.42rem;
      border-radius: 50%;
      background: var(--hydronicus-state-color);
      box-shadow: 0 0 0 0.28rem color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
      transform: translate(-50%, -50%);
    }
    .status-line { flex-wrap: wrap; margin-top: 0.48rem; gap: 0.35rem; }
    .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 650; }
    .status-dot { width: 0.45rem; height: 0.45rem; border-radius: 50%; background: var(--hydronicus-state-color); box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 40%, transparent); animation: hydronicus-pulse 2.8s ease-out infinite; }
    .mode-detail { border-left: 1px solid var(--hydronicus-border); padding-left: 0.55rem; }
    .source-line { margin-top: 0.35rem; }
    .source-line strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
    .badge, .phase, .state { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.69rem; line-height: 1.2; white-space: nowrap; }
    .badge { font-weight: 750; letter-spacing: 0.02em; background: color-mix(in srgb, var(--hydronicus-warning) 12%, transparent); }
    .badge.dry-run, .state.proposed { color: var(--hydronicus-warning); }
    .badge.mixed, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
    .badge.active, .state.active, .state.ready { color: var(--success-color, #287d34); }
    .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
    .mode-control { display: flex; align-items: center; min-height: 2.35rem; border: 1px solid var(--hydronicus-border); border-radius: 0.78rem; background: color-mix(in srgb, var(--hydronicus-surface) 36%, transparent); padding-left: 0.62rem; }
    .control-label { color: var(--hydronicus-muted); font-size: 0.7rem; font-weight: 650; letter-spacing: 0.04em; text-transform: uppercase; }
    button, select { min-height: 2.35rem; border: 1px solid var(--hydronicus-border); border-radius: 0.78rem; background: color-mix(in srgb, var(--hydronicus-surface) 44%, transparent); color: inherit; font: inherit; padding: 0.38rem 0.62rem; transition: border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease, transform 120ms ease; }
    .mode-control select { border: 0; background: transparent; min-height: 2.25rem; }
    button { cursor: pointer; }
    button:hover, select:hover { border-color: color-mix(in srgb, var(--hydronicus-state-color) 46%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-surface) 58%, transparent); }
    button:active { transform: translateY(1px); }
    button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
    button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--hydronicus-accent); outline-offset: 2px; }
    .shutdown { position: relative; overflow: hidden; color: var(--hydronicus-danger); }
    .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--hydronicus-danger) 18%, transparent); transform: scaleX(0); transform-origin: left; }
    .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
    .button-label { position: relative; z-index: 1; }
    .hold-progress { flex-basis: 100%; text-align: right; font-size: 0.67rem; color: var(--hydronicus-danger); }
    .alert, .error, .boundary { margin-top: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: 0.8rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); box-shadow: inset 0 1px 0 color-mix(in srgb, white 28%, transparent); padding: 0.68rem 0.75rem; }
    .alert { position: relative; overflow: hidden; padding-left: 0.9rem; }
    .alert::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--hydronicus-warning); }
    .alert.error::before, .error::before { background: var(--hydronicus-danger); }
    .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
    .boundary-orb { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; border-radius: 0.65rem; background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent); color: var(--hydronicus-state-color); }
    .boundary-orb::before { content: ""; width: 0.55rem; height: 0.55rem; border: 2px solid currentColor; border-radius: 50%; box-shadow: inset 0 0 0 2px color-mix(in srgb, currentColor 18%, transparent); }
    .boundary-copy { min-width: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
    .boundary-copy strong { font-size: 0.8rem; }
    section { margin-top: 1.05rem; }
    .section-head { justify-content: space-between; margin-bottom: 0.5rem; }
    .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
    .section-kicker::before { content: ""; width: 0.38rem; height: 0.38rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-state-color) 80%, transparent); }
    .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
    .zone, .path, .actuator, details { border: 1px solid var(--hydronicus-border); border-radius: 0.9rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); box-shadow: inset 0 1px 0 color-mix(in srgb, white 26%, transparent); }
    .zone, .path, .actuator { padding: 0.72rem; }
    .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
    .zone::before { content: ""; position: absolute; inset: 0 0 auto; height: 2px; background: var(--hydronicus-state-color); opacity: 0.18; transform: scaleX(0.35); transform-origin: left; transition: opacity 220ms ease, transform 380ms ease; }
    .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
    .zone[data-demand="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 30%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 7%, var(--hydronicus-surface) 38%); }
    .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 34%, var(--hydronicus-border)); }
    .row { justify-content: space-between; align-items: baseline; }
    .zone-title { min-width: 0; overflow-wrap: anywhere; }
    .zone-owner { margin-top: 0.12rem; }
    .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin: 0.65rem 0 0.5rem; }
    .metric { min-width: 0; border: 1px solid color-mix(in srgb, var(--hydronicus-border) 72%, transparent); border-radius: 0.72rem; background: color-mix(in srgb, var(--hydronicus-surface) 34%, transparent); padding: 0.52rem 0.58rem; }
    .metric.target { background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
    .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 680; letter-spacing: -0.035em; }
    .metric-unit { margin-left: 0.15rem; color: var(--hydronicus-muted); font-size: 0.72rem; }
    .metric-label { display: block; margin-top: 0.06rem; color: var(--hydronicus-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; }
    .zone-note { margin-top: 0.28rem; }
    .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.45rem; }
    .diagnostic-chip { border: 1px solid var(--hydronicus-border); border-radius: 999px; background: color-mix(in srgb, var(--hydronicus-surface) 28%, transparent); padding: 0.2rem 0.42rem; color: var(--hydronicus-muted); font-size: 0.64rem; }
    .diagnostic-chip.warning { color: var(--hydronicus-warning); border-color: color-mix(in srgb, var(--hydronicus-warning) 30%, var(--hydronicus-border)); }
    .diagnostic-chip.danger { color: var(--hydronicus-danger); border-color: color-mix(in srgb, var(--hydronicus-danger) 30%, var(--hydronicus-border)); }
    .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-top: 0.38rem; color: color-mix(in srgb, var(--hydronicus-warning) 80%, var(--hydronicus-muted)); }
    .coupling-note::before { content: ""; width: 0.34rem; height: 0.34rem; border: 1px solid currentColor; border-radius: 50%; box-shadow: 0.24rem 0 0 -1px color-mix(in srgb, currentColor 30%, transparent); }
    .zone-actions { display: flex; gap: 0.35rem; margin-top: 0.62rem; }
    .zone-actions button { min-width: 2.65rem; }
    .preset { flex: 1; min-width: 0; }
    .path-list, .actuator-list { display: grid; gap: 0.55rem; }
    .path { overflow: hidden; }
    .path-head { justify-content: space-between; flex-wrap: wrap; }
    .path-heading { display: flex; align-items: center; gap: 0.42rem; min-width: 0; }
    .path-heading::before { content: ""; flex: 0 0 auto; width: 0.43rem; height: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-muted) 55%, transparent); }
    .path[data-flowing="true"] .path-heading::before { background: var(--hydronicus-state-color); box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 36%, transparent); animation: hydronicus-pulse 2.4s ease-out infinite; }
    .path[data-status="blocked"] .path-heading::before { background: var(--hydronicus-danger); }
    .path-track { display: flex; align-items: stretch; margin-top: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding: 0.08rem 0.03rem 0.25rem; scroll-snap-type: inline proximity; scrollbar-color: color-mix(in srgb, var(--hydronicus-state-color) 25%, transparent) transparent; scrollbar-width: thin; }
    .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-width: 0; border: 1px solid var(--hydronicus-border); border-radius: 0.72rem; background: color-mix(in srgb, var(--hydronicus-surface) 38%, transparent); padding: 0.48rem 0.52rem; font-size: 0.74rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, box-shadow 220ms ease, background-color 220ms ease; }
    .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 34%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 8%, var(--hydronicus-surface) 38%); box-shadow: inset 0 1px 0 color-mix(in srgb, white 22%, transparent); }
    .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 36%, var(--hydronicus-border)); }
    .node-kind { color: var(--hydronicus-muted); font-size: 0.59rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
    .node-name { margin-top: 0.18rem; font-weight: 620; line-height: 1.25; }
    .node-state { display: flex; align-items: center; gap: 0.28rem; margin-top: 0.3rem; color: var(--hydronicus-muted); font-size: 0.64rem; }
    .node-state::before { content: ""; width: 0.3rem; height: 0.3rem; border-radius: 50%; background: currentColor; }
    .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); }
    .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-width: 1.2rem; align-self: center; height: 2px; margin: 0 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--hydronicus-muted) 24%, transparent); }
    .flow-link::before { content: ""; position: absolute; right: 0; top: 50%; width: 0.34rem; height: 0.34rem; border-top: 1px solid var(--hydronicus-muted); border-right: 1px solid var(--hydronicus-muted); transform: translateY(-50%) rotate(45deg); }
    .flow-link::after { content: ""; position: absolute; inset: -1px auto -1px 0; width: 58%; background: linear-gradient(90deg, transparent, var(--hydronicus-state-color), transparent); opacity: 0; transform: translateX(-120%); }
    .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent); }
    .path[data-flowing="true"] .flow-link::before { border-color: var(--hydronicus-state-color); }
    .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--hydronicus-flow-duration) linear infinite; }
    .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--hydronicus-danger) 30%, transparent); }
    .path-problem { margin-top: 0.5rem; color: var(--hydronicus-danger); }
    .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
    .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
    .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.48rem; }
    .consumer-chip { max-width: 100%; border: 1px solid var(--hydronicus-border); border-radius: 999px; background: color-mix(in srgb, var(--hydronicus-surface) 32%, transparent); padding: 0.2rem 0.42rem; color: var(--hydronicus-muted); font-size: 0.66rem; overflow-wrap: anywhere; }
    .consumer-chip strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
    details { overflow: hidden; padding: 0.62rem 0.72rem; }
    details + details { margin-top: 0.45rem; }
    summary { cursor: pointer; font-size: 0.82rem; font-weight: 650; }
    details[open] summary { margin-bottom: 0.25rem; }
    details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
    .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding: 0.48rem 0; border-top: 1px solid var(--hydronicus-border); font-size: 0.8rem; }
    .operation:first-child { border-top: 0; }
    .operation-marker { width: 0.4rem; height: 0.4rem; margin-top: 0.35rem; border-radius: 50%; background: var(--hydronicus-muted); }
    .operation[data-result="proposed"] .operation-marker { background: var(--hydronicus-warning); }
    .operation[data-result="executed"] .operation-marker { background: var(--success-color, #287d34); }
    .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--hydronicus-danger); }
    .operation-copy { min-width: 0; }
    .empty-state { padding: 0.8rem; border: 1px dashed var(--hydronicus-border); border-radius: 0.8rem; text-align: center; }
    .loading-card { min-height: 12rem; }
    .loading-head { display: flex; align-items: center; gap: 0.65rem; }
    .loading-mark, .skeleton { background: linear-gradient(105deg, color-mix(in srgb, var(--hydronicus-surface) 30%, transparent) 20%, color-mix(in srgb, white 24%, transparent) 38%, color-mix(in srgb, var(--hydronicus-surface) 30%, transparent) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
    .loading-mark { width: 2.7rem; height: 2.7rem; border-radius: 1rem; }
    .skeleton { width: min(16rem, 62cqi); height: 0.72rem; border-radius: 999px; }
    .skeleton.short { width: min(10rem, 42cqi); margin-top: 0.45rem; }
    .loading-panel { height: 4.2rem; margin-top: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: 0.9rem; }
    @container (max-width: 680px) {
      .header { display: block; }
      .controls { justify-content: flex-start; margin-top: 0.7rem; }
      .hold-progress { text-align: left; }
    }
    @container (max-width: 440px) {
      .zone-grid { grid-template-columns: 1fr; }
      .mode-detail { flex-basis: 100%; border-left: 0; padding-left: 0; }
      .boundary-copy { display: block; }
      .boundary-copy .control-label { display: block; margin-bottom: 0.12rem; }
      .section-head { align-items: flex-start; }
      .section-head > .meta { text-align: right; }
    }
    @media (max-width: 560px) {
      .card { padding: 0.75rem; }
      .controls { justify-content: flex-start; }
    }
    @media (prefers-reduced-motion: reduce) {
      .card, .card::before, .plant-mark::before, .status-dot, .path-heading::before, .path[data-flowing="true"] .flow-link::after, details[open] .operation, .loading-mark, .skeleton { animation: none !important; }
      button, select, .zone, .node { transition-duration: 0.01ms !important; }
      .path[data-flowing="true"] .flow-link::after { opacity: 0.65; transform: translateX(40%); }
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
      0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--hydronicus-state-color) 38%, transparent); }
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
  `;hass;_config;_snapshot=null;_error=null;_reconnecting=false;_holdingShutdown=false;_unsubscribe=null;_holdTimer=null;_subscriptionGeneration=0;setConfig(e){if(!e||e.type!=="custom:hydronicus-plant-card"||typeof e.plant!=="string"||!e.plant){throw new Error("Hydronicus Plant card requires one Plant UUID.")}if(e.density&&!["comfortable","compact"].includes(e.density)){throw new Error("Hydronicus Plant card density must be comfortable or compact.")}this._config={...e,density:e.density??"comfortable"};this._subscribe()}getCardSize(){return 7}getGridOptions(){return{rows:6,columns:6,min_rows:4,min_columns:3,max_columns:12}}connectedCallback(){super.connectedCallback();this._subscribe()}disconnectedCallback(){this._unsubscribe?.();this._unsubscribe=null;this._subscriptionGeneration+=1;this._clearHold();super.disconnectedCallback()}updated(){this._subscribe()}render(){const e=this._snapshot;const t=this._config;if(!t)return i`<div class="card" role="status"><div class="empty-state">Configure one Hydronicus Plant.</div></div>`;if(this._error)return i`<div class="card" data-visual="attention" role="alert"><div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">Connection needs attention</p><h1>Hydronicus Plant</h1></div></div><p class="error">${this._error}</p><p class="meta">Check the Dashboard Resource and wait for the connection to recover.</p></div>`;if(!e)return i`<div class="card loading-card" role="status" aria-busy="true"><div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div><div class="loading-panel"></div><p class="muted">${this._reconnecting?"Reconnecting to Hydronicus\u2026":"Loading Plant snapshot\u2026"}</p></div>`;return i`<article class="card ${t.density}" data-visual=${$e(e)} aria-label=${e.plant.name}>
      ${this._renderHeader(e)}
      <div class="boundary" role="status">
        <span class="boundary-orb" aria-hidden="true"></span>
        <div class="boundary-copy"><span class="control-label">Execution boundary</span><strong>${e.plant.execution_boundary.message||`${u(e.plant.execution_boundary.mode)} execution boundary is active.`}</strong></div>
      </div>
      ${this._renderAlerts(e)}
      ${this._renderZones(e)}
      ${this._renderPaths(e)}
      ${this._renderActuators(e)}
      ${this._renderExplanations(e)}
      ${this._renderOperations(e)}
    </article>`}_renderHeader(e){const t=e.plant.execution_boundary;return i`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h1>${e.plant.name}</h1>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${u(e.plant.status)}</span>
            <span class="meta mode-detail">Requested ${u(e.plant.requested_mode)} · active ${u(e.plant.active_mode)}</span>
          </div>
          <p class="meta source-line"><strong>Source</strong> ${e.plant.source.active_name??"none active"} · recommended ${e.plant.source.recommended_name??"none"}</p>
          <p class="meta">${e.plant.controller.mode_explanation??"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${t.mode}" aria-label="Execution boundary">${u(t.mode)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" .value=${e.plant.requested_mode} @change=${this._modeChanged}>
          ${Fe.map(r=>i`<option value=${r}>${u(r)}</option>`)}
        </select></label>
        ${this._renderShutdown(e)}
      </div>
    </header>`}_renderShutdown(e){const t=!e.controls.safe_shutdown;return i`<button class=${`shutdown ${this._holdingShutdown?"is-holding":""}`} ?disabled=${t} aria-label="Hold to confirm Hydronicus Safe shutdown" aria-pressed=${this._holdingShutdown?"true":"false"} @pointerdown=${this._startHold} @pointerup=${this._clearHold} @pointercancel=${this._clearHold} @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd}><span class="button-label">Safe shutdown</span></button>${this._holdingShutdown?i`<span class="hold-progress" role="status">Keep holding…</span>`:d}`}_renderAlerts(e){const t=_e(e);if(!t.length)return d;return i`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-alerts">Alerts</h2></div><span class="meta">${t.length}</span></div>${t.slice(0,3).map(r=>i`<div class="alert ${r.severity==="error"||r.severity==="critical"?"error":""}" data-severity=${r.severity} role=${r.severity==="error"||r.severity==="critical"?"alert":"status"}><strong>${u(r.code)}</strong><span> · ${r.message}</span></div>`)}</section>`}_renderZones(e){return i`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-zones">Comfort Zones</h2></div><span class="meta">${e.zones.length} visible</span></div><div class="zone-grid">${e.zones.length?e.zones.map(t=>this._renderZone(e,t)):i`<p class="muted empty-state">No visible Zones are configured for this Plant.</p>`}</div></section>`}_renderZone(e,t){const r=t.thermostat;const n=r.current_temperature===null?"--":r.current_temperature.toFixed(1);const o=r.target_temperature===null?"--":r.target_temperature.toFixed(1);const a=r.kind==="hydronicus";const h=t.demand||t.cooling.demand;return i`<article class="zone" data-phase=${t.phase} data-demand=${String(h)} data-blocked=${String(t.blocked)} aria-label=${`${t.name} Zone`}>
      <div class="row"><div><h3 class="zone-title">${t.name}</h3><p class="meta zone-owner">${a?"Hydronicus thermostat":"External thermostat \xB7 read-only"}</p></div><span class="phase ${t.blocked?"state blocked":""}">${u(t.phase)}</span></div>
      <div class="temperature-panel">
        <div class="metric" aria-label=${`Current temperature ${r.current_temperature===null?"unavailable":`${n} degrees Celsius`}`}><span class="metric-value">${n}</span>${r.current_temperature===null?d:i`<span class="metric-unit">°C</span>`}<span class="metric-label">Current</span></div>
        <div class="metric target" aria-label=${`Target temperature ${r.target_temperature===null?"unavailable":`${o} degrees Celsius`}`}><span class="metric-value">${o}</span>${r.target_temperature===null?d:i`<span class="metric-unit">°C</span>`}<span class="metric-label">Target</span></div>
      </div>
      <p class="meta zone-note">${h?`${t.cooling.demand?"Cooling":"Heating"} demand active`:"No demand"} · ${r.explanation}</p>
      <div class="diagnostic-list" aria-label="Zone diagnostics">
        <span class="diagnostic-chip">${t.sensor_status.usable} sensor${t.sensor_status.usable===1?"":"s"} ready</span>
        ${t.sensor_status.optional_excluded?i`<span class="diagnostic-chip warning">${t.sensor_status.optional_excluded} optional excluded</span>`:d}
        ${t.sensor_status.required_blocking?i`<span class="diagnostic-chip danger">${t.sensor_status.required_blocking} required blocked</span>`:d}
        ${t.cooling.dew_point===null?d:i`<span class="diagnostic-chip">Dew point ${t.cooling.dew_point.toFixed(1)} °C</span>`}
        ${t.cooling.condensation_margin===null?d:i`<span class="diagnostic-chip ${t.cooling.blocked?"danger":""}">Margin ${t.cooling.condensation_margin.toFixed(1)} °C</span>`}
      </div>
      ${r.preset?i`<p class="meta zone-note">Preset: ${u(r.preset)}</p>`:d}
      ${t.blocked_reason?i`<p class="meta zone-note" role="status">${t.blocked_reason}</p>`:d}
      ${t.coupling_group_ids.length?i`<p class="meta coupling-note">Coupled delivery - this Zone shares hydraulic equipment.</p>`:d}
      ${a?i`<div class="zone-actions"><button ?disabled=${!r.control_entity_id||r.target_temperature===null} aria-label=${`Decrease ${t.name} target by half a degree`} @click=${()=>this._adjustZone(t,-.5)}>−0.5</button><button ?disabled=${!r.control_entity_id||r.target_temperature===null} aria-label=${`Increase ${t.name} target by half a degree`} @click=${()=>this._adjustZone(t,.5)}>+0.5</button><select class="preset" aria-label=${`${t.name} preset`} .value=${r.preset??"none"} ?disabled=${!r.control_entity_id} @change=${l=>this._presetChanged(t,l)}>${["none",...r.preset_modes].map(l=>i`<option value=${l}>${u(l)}</option>`)}</select></div>`:i`<p class="meta" role="note">Adjust this thermostat in its owning Home Assistant integration.</p>`}
    </article>`}_renderPaths(e){if(!e.delivery_paths.length)return d;return i`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-paths">Hydraulic Flow</h2></div><span class="meta">Zone → Circuit → Valve → Pump → Source</span></div><div class="path-list">${e.delivery_paths.map(t=>i`<article class="path" data-status=${t.status} data-flowing=${String(J(t.status))}><div class="path-head"><div class="path-heading"><strong>${e.zones.find(r=>r.id===t.zone_id)?.name??t.zone_id}</strong></div><div class="status-line"><span class="state ${t.status}">${u(t.status)}</span>${t.coupled?i`<span class="meta">coupled</span>`:d}</div></div><div class="path-track" aria-label="Ordered hydraulic delivery path">${t.nodes.map((r,n)=>i`${n?i`<span class="flow-link" aria-hidden="true"></span>`:d}<span class="node" data-kind=${r.kind} data-state=${r.state} data-flowing=${String(J(r.state))} title=${`${r.name}: ${u(r.state)}`}><span class="node-kind">${u(r.kind)}</span><span class="node-name">${r.name}</span><span class="node-state">${u(r.state)}</span></span>`)}</div>${t.problem?i`<p class="meta path-problem" role="alert">${t.problem}</p>`:d}</article>`)}</div></section>`}_renderActuators(e){if(!e.actuators.length)return d;return i`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h2 id="hydronicus-actuators">Actuator Ownership</h2></div><span class="meta">Shared consumers stay visible</span></div><div class="actuator-list">${e.actuators.map(t=>i`<article class="actuator" data-state=${t.state}><div class="row"><strong>${t.name}</strong><span class="state actuator-state ${t.state}">${u(t.state)}</span></div><p class="meta">${u(t.kind)} · ${t.reason??"No additional explanation."}</p>${t.active_consumers.length?i`<div class="consumer-list" aria-label="Active circuit consumers">${t.active_consumers.map(r=>i`<span class="consumer-chip"><strong>${r.name}</strong> · ${r.id}</span>`)}</div>`:i`<p class="meta zone-note">No active circuit consumers.</p>`}</article>`)}</div></section>`}_renderExplanations(e){return i`<section aria-labelledby="hydronicus-explanations"><details><summary id="hydronicus-explanations">Controller explanations</summary>${e.explanations.map(t=>i`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${u(t.scope)}</strong> · ${t.message}</p></div>`)}</details></section>`}_renderOperations(e){const t=Object.values(e.execution.operations).flat();if(!t.length)return d;return i`<section aria-labelledby="hydronicus-operations"><details open><summary id="hydronicus-operations">Latest operation outcomes (${t.length})</summary>${t.map(r=>{const n=String(r.result??"unknown");return i`<div class="operation" data-result=${n}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${Ae(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}_subscribe(){if(!this._config||!this.hass||this._unsubscribe)return;const e=++this._subscriptionGeneration;this._reconnecting=false;this._error=null;this.hass.connection.subscribeMessage(t=>{if(e!==this._subscriptionGeneration)return;const r=t.snapshot;if(!r)return;try{this._snapshot=ve(r);this._error=null;this._reconnecting=false}catch(n){this._snapshot=null;this._error=n instanceof Error?n.message:"Unsupported Hydronicus snapshot."}},{type:"hydronicus/subscribe_plant",plant_id:this._config.plant}).then(t=>{if(e!==this._subscriptionGeneration){t();return}this._unsubscribe=t}).catch(t=>{if(e!==this._subscriptionGeneration)return;this._reconnecting=true;this._error=t instanceof Error?t.message:"Hydronicus connection failed."})}_call(e){if(!e||!this.hass)return;void this.hass.callService(e.domain,e.service,e.data).catch(t=>{this._error=t instanceof Error?t.message:"Home Assistant action failed."})}_modeChanged=e=>{if(!this._snapshot)return;this._call(ke(this._snapshot,e.target.value))};_adjustZone(e,t){const r=Ce(e,t);if(r!==null)this._call(xe(e,r))}_presetChanged(e,t){this._call(we(e,t.target.value))}_startHold=()=>{if(!this._snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=window.setTimeout(()=>{if(!this._snapshot)return;this._call(Se(this._snapshot));this._holdingShutdown=false;this._holdTimer=null},1200)};_clearHold=()=>{if(this._holdTimer!==null)window.clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_keyHoldStart=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();this._startHold()}};_keyHoldEnd=e=>{if(e.key==="Enter"||e.key===" ")this._clearHold()};static getConfigElement(){return document.createElement("hydronicus-plant-card-editor")}static getStubConfig(){return{plant:"",density:"comfortable"}}};var ee=class extends f{static properties={hass:{attribute:false},_config:{state:true},_plants:{state:true},_error:{state:true}};static styles=R`
    :host { display: block; padding: 1rem; }
    label { display: grid; gap: 0.35rem; margin-bottom: 0.8rem; }
    select { box-sizing: border-box; min-height: 2.4rem; padding: 0.4rem; font: inherit; color: inherit; background: var(--card-background-color, transparent); border: 1px solid var(--divider-color); border-radius: 0.45rem; }
    select:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }
  `;hass;_config={type:"custom:hydronicus-plant-card",plant:"",density:"comfortable"};_plants=[];_error=null;_loaded=false;setConfig(e){this._config={...this._config,...e};this._loadPlants()}updated(){this._loadPlants()}render(){return i`<label>Hydronicus Plant<select aria-label="Hydronicus Plant" .value=${this._config.plant} @change=${this._plantChanged}><option value="">Select a Plant…</option>${this._plants.map(e=>i`<option value=${e.id}>${e.name}</option>`)}</select></label><label>Density<select aria-label="Card density" .value=${this._config.density??"comfortable"} @change=${this._densityChanged}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label>${this._error?i`<p role="alert">${this._error}</p>`:d}`}_loadPlants(){if(!this.hass||this._loaded)return;this._loaded=true;this.hass.connection.sendMessagePromise({type:"hydronicus/list_plants"}).then(e=>{this._plants=e.plants??[]}).catch(e=>{this._error=e instanceof Error?e.message:"Could not list Hydronicus Plants."})}_configChanged(){this.dispatchEvent(new CustomEvent("config-changed",{bubbles:true,composed:true,detail:{config:this._config}}))}_plantChanged=e=>{this._config={...this._config,plant:e.target.value};this._configChanged()};_densityChanged=e=>{this._config={...this._config,density:e.target.value};this._configChanged()}};customElements.define("hydronicus-plant-card",Q);customElements.define("hydronicus-plant-card-editor",ee);window.customCards=window.customCards??[];window.customCards.push({type:"hydronicus-plant-card",name:"Hydronicus Plant",version:"0.1.0-rc.4",description:"Topology-driven Hydronicus Plant status and controls.",preview:false,documentationURL:"https://github.com/brumi1024/ha-hydronicus"});
