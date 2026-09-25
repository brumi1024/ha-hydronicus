var T="hydronicus-plant-card";var Ue=`custom:${T}`;var Bt="hydronicus/list_plants";var Wt=["comfortable","compact"];var qe=[{value:"header",label:"Header and execution boundary"},{value:"alerts",label:"Alerts"},{value:"rooms",label:"Rooms"},{value:"paths",label:"Hydraulic flow"},{value:"equipment",label:"Equipment"},{value:"explanations",label:"Controller explanations"},{value:"operations",label:"Operation outcomes"}];var re=qe.map(n=>n.value);function Kt(n,e,t){if(!n||typeof n!=="object"){throw new Error(`${e} requires a configuration.`)}const r=n;if(r.type!==t){throw new Error(`${e} type must be ${t}.`)}if(typeof r.plant!=="string"){throw new Error(`${e} requires one Plant UUID in \`plant\`.`)}return r}function Xt(n,e){const t=n??"comfortable";if(!Wt.includes(t)){throw new Error(`${e} density must be comfortable or compact.`)}return t}function Yt(n){if(n===void 0||n===null)return void 0;if(!Array.isArray(n)){throw new Error("Hydronicus Plant card `sections` must be a list of section names.")}const e=new Set;for(const t of n){if(typeof t!=="string"||!re.includes(t)){throw new Error(`Hydronicus Plant card section ${JSON.stringify(t)} is unknown. Use ${re.join(", ")}.`)}if(e.has(t)){throw new Error(`Hydronicus Plant card section ${t} is listed twice.`)}e.add(t)}return n.length?n:void 0}function se(n){const e="Hydronicus Plant card";const t=Kt(n,e,Ue);const r=Xt(t.density,e);const o=Yt(t.sections);return{type:Ue,plant:t.plant.trim(),density:r,...o?{sections:o}:{}}}function W(n){return n?.sections??re}var oe=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(e){if(this.connection===e&&this.pending)return this.pending;this.connection=e;this.pending=e.sendMessagePromise({type:Bt}).then(t=>{this.plants=Array.isArray(t.plants)?t.plants:[];return this.plants}).catch(()=>{if(this.connection===e)this.pending=null;return this.plants});return this.pending}async settled(e=2e3){if(!this.pending)return this.plants;let t;const r=new Promise(o=>{t=setTimeout(()=>o(this.plants),e)});try{return await Promise.race([this.pending,r])}finally{clearTimeout(t)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var U=new oe;async function Ne(n){const e=n?.connection?await U.load(n.connection):U.known;return{plant:e[0]?.id??"",density:"comfortable"}}var Zt={plant:"Hydronicus Plant",density:"Density",sections:"Sections"};var Gt={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",density:"Compact uses less spacing for dense dashboards.",sections:"The parts of the Plant to show, in this order. Leave empty to show every section."};var Jt=n=>Zt[n.name];var Qt=n=>Gt[n.name];function en(n){if(n.length===0)return{text:{}};return{select:{mode:"dropdown",options:n.map(e=>({value:e.id,label:e.name}))}}}var tn={name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}};async function Oe(){const n=await U.settled();return{schema:[{name:"plant",required:true,selector:en(n)},tn,{name:"sections",selector:{select:{multiple:true,reorder:true,mode:"dropdown",options:qe.map(e=>({...e}))}}}],computeLabel:Jt,computeHelper:Qt,assertConfig:e=>{se(e)}}}var K=globalThis;var X=K.ShadowRoot&&(void 0===K.ShadyCSS||K.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var ie=Symbol();var De=new WeakMap;var q=class{constructor(e,t,r){if(this._$cssResult$=true,r!==ie)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o;const t=this.t;if(X&&void 0===e){const r=void 0!==t&&1===t.length;r&&(e=De.get(t)),void 0===e&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&De.set(t,e))}return e}toString(){return this.cssText}};var Ie=n=>new q("string"==typeof n?n:n+"",void 0,ie);var ae=(n,...e)=>{const t=1===n.length?n[0]:e.reduce((r,o,s)=>r+(i=>{if(true===i._$cssResult$)return i.cssText;if("number"==typeof i)return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[s+1],n[0]);return new q(t,n,ie)};var Fe=(n,e)=>{if(X)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const t of e){const r=document.createElement("style"),o=K.litNonce;void 0!==o&&r.setAttribute("nonce",o),r.textContent=t.cssText,n.appendChild(r)}};var le=X?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(const r of e.cssRules)t+=r.cssText;return Ie(t)})(n):n;var{is:nn,defineProperty:rn,getOwnPropertyDescriptor:on,getOwnPropertyNames:sn,getOwnPropertySymbols:an,getPrototypeOf:ln}=Object;var Y=globalThis;var je=Y.trustedTypes;var cn=je?je.emptyScript:"";var dn=Y.reactiveElementPolyfillSupport;var N=(n,e)=>n;var ce={toAttribute(n,e){switch(e){case Boolean:n=n?cn:null;break;case Object:case Array:n=null==n?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=null!==n;break;case Number:t=null===n?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch(r){t=null}}return t}};var Be=(n,e)=>!nn(n,e);var Ve={attribute:true,type:String,converter:ce,reflect:false,useDefault:false,hasChanged:Be};Symbol.metadata??=Symbol("metadata"),Y.litPropertyMetadata??=new WeakMap;var v=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Ve){if(t.state&&(t.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=true),this.elementProperties.set(e,t),!t.noAccessor){const r=Symbol(),o=this.getPropertyDescriptor(e,r,t);void 0!==o&&rn(this.prototype,e,o)}}static getPropertyDescriptor(e,t,r){const{get:o,set:s}=on(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:o,set(i){const u=o?.call(this);s?.call(this,i),this.requestUpdate(e,u,r)},configurable:true,enumerable:true}}static getPropertyOptions(e){return this.elementProperties.get(e)??Ve}static _$Ei(){if(this.hasOwnProperty(N("elementProperties")))return;const e=ln(this);e.finalize(),void 0!==e.l&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(N("properties"))){const t=this.properties,r=[...sn(t),...an(t)];for(const o of r)this.createProperty(o,t[o])}const e=this[Symbol.metadata];if(null!==e){const t=litPropertyMetadata.get(e);if(void 0!==t)for(const[r,o]of t)this.elementProperties.set(r,o)}this._$Eh=new Map;for(const[t,r]of this.elementProperties){const o=this._$Eu(t,r);void 0!==o&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){const t=[];if(Array.isArray(e)){const r=new Set(e.flat(1/0).reverse());for(const o of r)t.unshift(le(o))}else void 0!==e&&t.push(le(e));return t}static _$Eu(e,t){const r=t.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof e?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),void 0!==this.renderRoot&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){const e=new Map,t=this.constructor.elementProperties;for(const r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){const e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Fe(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){const r=this.constructor.elementProperties.get(e),o=this.constructor._$Eu(e,r);if(void 0!==o&&true===r.reflect){const s=(void 0!==r.converter?.toAttribute?r.converter:ce).toAttribute(t,r.type);this._$Em=e,null==s?this.removeAttribute(o):this.setAttribute(o,s),this._$Em=null}}_$AK(e,t){const r=this.constructor,o=r._$Eh.get(e);if(void 0!==o&&this._$Em!==o){const s=r.getPropertyOptions(o),i="function"==typeof s.converter?{fromAttribute:s.converter}:void 0!==s.converter?.fromAttribute?s.converter:ce;this._$Em=o;const u=i.fromAttribute(t,s.type);this[o]=u??this._$Ej?.get(o)??u,this._$Em=null}}requestUpdate(e,t,r,o=false,s){if(void 0!==e){const i=this.constructor;if(false===o&&(s=this[e]),r??=i.getPropertyOptions(e),!((r.hasChanged??Be)(s,t)||r.useDefault&&r.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,r))))return;this.C(e,t,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:o,wrapped:s},i){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),true!==s||void 0!==i)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),true===o&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(t){Promise.reject(t)}const e=this.scheduleUpdate();return null!=e&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[o,s]of this._$Ep)this[o]=s;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[o,s]of r){const{wrapped:i}=s,u=this[o];true!==i||this._$AL.has(o)||void 0===u||this.C(o,void 0,s,u)}}let e=false;const t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=false,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return true}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[N("elementProperties")]=new Map,v[N("finalized")]=new Map,dn?.({ReactiveElement:v}),(Y.reactiveElementVersions??=[]).push("2.1.2");var ge=globalThis;var We=n=>n;var Z=ge.trustedTypes;var Ke=Z?Z.createPolicy("lit-html",{createHTML:n=>n}):void 0;var Qe="$lit$";var x=`lit$${Math.random().toFixed(9).slice(2)}$`;var et="?"+x;var un=`<${et}>`;var C=document;var D=()=>C.createComment("");var I=n=>null===n||"object"!=typeof n&&"function"!=typeof n;var be=Array.isArray;var pn=n=>be(n)||"function"==typeof n?.[Symbol.iterator];var de="[ 	\n\f\r]";var O=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Xe=/-->/g;var Ye=/>/g;var w=RegExp(`>|${de}(?:([^\\s"'>=/]+)(${de}*=${de}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Ze=/'/g;var Ge=/"/g;var tt=/^(?:script|style|textarea|title)$/i;var ye=n=>(e,...t)=>({_$litType$:n,strings:e,values:t});var a=ye(1);var Yn=ye(2);var Zn=ye(3);var A=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var Je=new WeakMap;var k=C.createTreeWalker(C,129);function nt(n,e){if(!be(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Ke?Ke.createHTML(e):e}var hn=(n,e)=>{const t=n.length-1,r=[];let o,s=2===e?"<svg>":3===e?"<math>":"",i=O;for(let u=0;u<t;u++){const l=n[u];let d,h,p=-1,m=0;for(;m<l.length&&(i.lastIndex=m,h=i.exec(l),null!==h);)m=i.lastIndex,i===O?"!--"===h[1]?i=Xe:void 0!==h[1]?i=Ye:void 0!==h[2]?(tt.test(h[2])&&(o=RegExp("</"+h[2],"g")),i=w):void 0!==h[3]&&(i=w):i===w?">"===h[0]?(i=o??O,p=-1):void 0===h[1]?p=-2:(p=i.lastIndex-h[2].length,d=h[1],i=void 0===h[3]?w:'"'===h[3]?Ge:Ze):i===Ge||i===Ze?i=w:i===Xe||i===Ye?i=O:(i=w,o=void 0);const g=i===w&&n[u+1].startsWith("/>")?" ":"";s+=i===O?l+un:p>=0?(r.push(d),l.slice(0,p)+Qe+l.slice(p)+x+g):l+x+(-2===p?u:g)}return[nt(n,s+(n[t]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),r]};var F=class n{constructor({strings:e,_$litType$:t},r){let o;this.parts=[];let s=0,i=0;const u=e.length-1,l=this.parts,[d,h]=hn(e,t);if(this.el=n.createElement(d,r),k.currentNode=this.el.content,2===t||3===t){const p=this.el.content.firstChild;p.replaceWith(...p.childNodes)}for(;null!==(o=k.nextNode())&&l.length<u;){if(1===o.nodeType){if(o.hasAttributes())for(const p of o.getAttributeNames())if(p.endsWith(Qe)){const m=h[i++],g=o.getAttribute(p).split(x),S=/([.?@])?(.*)/.exec(m);l.push({type:1,index:s,name:S[2],strings:g,ctor:"."===S[1]?pe:"?"===S[1]?he:"@"===S[1]?me:z}),o.removeAttribute(p)}else p.startsWith(x)&&(l.push({type:6,index:s}),o.removeAttribute(p));if(tt.test(o.tagName)){const p=o.textContent.split(x),m=p.length-1;if(m>0){o.textContent=Z?Z.emptyScript:"";for(let g=0;g<m;g++)o.append(p[g],D()),k.nextNode(),l.push({type:2,index:++s});o.append(p[m],D())}}}else if(8===o.nodeType)if(o.data===et)l.push({type:2,index:s});else{let p=-1;for(;-1!==(p=o.data.indexOf(x,p+1));)l.push({type:7,index:s}),p+=x.length-1}s++}}static createElement(e,t){const r=C.createElement("template");return r.innerHTML=e,r}};function H(n,e,t=n,r){if(e===A)return e;let o=void 0!==r?t._$Co?.[r]:t._$Cl;const s=I(e)?void 0:e._$litDirective$;return o?.constructor!==s&&(o?._$AO?.(false),void 0===s?o=void 0:(o=new s(n),o._$AT(n,t,r)),void 0!==r?(t._$Co??=[])[r]=o:t._$Cl=o),void 0!==o&&(e=H(n,o._$AS(n,e.values),o,r)),e}var ue=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){const{el:{content:t},parts:r}=this._$AD,o=(e?.creationScope??C).importNode(t,true);k.currentNode=o;let s=k.nextNode(),i=0,u=0,l=r[0];for(;void 0!==l;){if(i===l.index){let d;2===l.type?d=new j(s,s.nextSibling,this,e):1===l.type?d=new l.ctor(s,l.name,l.strings,this,e):6===l.type&&(d=new fe(s,this,e)),this._$AV.push(d),l=r[++u]}i!==l?.index&&(s=k.nextNode(),i++)}return k.currentNode=C,o}p(e){let t=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}};var j=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,o){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??true}get parentNode(){let e=this._$AA.parentNode;const t=this._$AM;return void 0!==t&&11===e?.nodeType&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=H(this,e,t),I(e)?e===c||null==e||""===e?(this._$AH!==c&&this._$AR(),this._$AH=c):e!==this._$AH&&e!==A&&this._(e):void 0!==e._$litType$?this.$(e):void 0!==e.nodeType?this.T(e):pn(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==c&&I(this._$AH)?this._$AA.nextSibling.data=e:this.T(C.createTextNode(e)),this._$AH=e}$(e){const{values:t,_$litType$:r}=e,o="number"==typeof r?this._$AC(e):(void 0===r.el&&(r.el=F.createElement(nt(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(t);else{const s=new ue(o,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=Je.get(e.strings);return void 0===t&&Je.set(e.strings,t=new F(e)),t}k(e){be(this._$AH)||(this._$AH=[],this._$AR());const t=this._$AH;let r,o=0;for(const s of e)o===t.length?t.push(r=new n(this.O(D()),this.O(D()),this,this.options)):r=t[o],r._$AI(s),o++;o<t.length&&(this._$AR(r&&r._$AB.nextSibling,o),t.length=o)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(false,true,t);e!==this._$AB;){const r=We(e).nextSibling;We(e).remove(),e=r}}setConnected(e){void 0===this._$AM&&(this._$Cv=e,this._$AP?.(e))}};var z=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,o,s){this.type=1,this._$AH=c,this._$AN=void 0,this.element=e,this.name=t,this._$AM=o,this.options=s,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=c}_$AI(e,t=this,r,o){const s=this.strings;let i=false;if(void 0===s)e=H(this,e,t,0),i=!I(e)||e!==this._$AH&&e!==A,i&&(this._$AH=e);else{const u=e;let l,d;for(e=s[0],l=0;l<s.length-1;l++)d=H(this,u[r+l],t,l),d===A&&(d=this._$AH[l]),i||=!I(d)||d!==this._$AH[l],d===c?e=c:e!==c&&(e+=(d??"")+s[l+1]),this._$AH[l]=d}i&&!o&&this.j(e)}j(e){e===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}};var pe=class extends z{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===c?void 0:e}};var he=class extends z{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==c)}};var me=class extends z{constructor(e,t,r,o,s){super(e,t,r,o,s),this.type=5}_$AI(e,t=this){if((e=H(this,e,t,0)??c)===A)return;const r=this._$AH,o=e===c&&r!==c||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,s=e!==c&&(r===c||o);o&&this.element.removeEventListener(this.name,this,r),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}};var fe=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){H(this,e)}};var mn=ge.litHtmlPolyfillSupport;mn?.(F,j),(ge.litHtmlVersions??=[]).push("3.3.3");var rt=(n,e,t)=>{const r=t?.renderBefore??e;let o=r._$litPart$;if(void 0===o){const s=t?.renderBefore??null;r._$litPart$=o=new j(e.insertBefore(D(),s),s,void 0,t??{})}return o._$AI(n),o};var ve=globalThis;var $=class extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){const t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=rt(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return A}};$._$litElement$=true,$["finalized"]=true,ve.litElementHydrateSupport?.({LitElement:$});var fn=ve.litElementPolyfillSupport;fn?.({LitElement:$});(ve.litElementVersions??=[]).push("4.2.2");var E=class extends Event{constructor(e,t,r,o){super("context-request",{bubbles:true,composed:true}),this.context=e,this.contextTarget=t,this.callback=r,this.subscribe=o??false}};function L(n){return n}var _=class{constructor(e,t,r,o){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(s,i)=>{this.unsubscribe&&(this.unsubscribe!==i&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=s,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(s,i)),this.unsubscribe=i},this.host=e,void 0!==t.context){const s=t;this.context=s.context,this.callback=s.callback,this.subscribe=s.subscribe??false}else this.context=t,this.callback=r,this.subscribe=o??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new E(this.context,this.host,this.t,this.subscribe))}};var P="\xB0C";var bn=5;var yn=35;function _e(n){return n?.temperature==="\xB0F"?"\xB0F":P}function G(n,e){return e==="\xB0F"?n*9/5+32:n}function vn(n,e){return e==="\xB0F"?n*9/5:n}function xe(n){return n==="\xB0F"?1:.5}function st(n,e,t){const r=xe(t);const o=G(n,t);const s=o/r;const i=(e>0?Math.floor(s+1e-9)+1:Math.ceil(s-1e-9)-1)*r;const u=G(bn,t);const l=G(yn,t);return Number(Math.min(l,Math.max(u,i)).toFixed(1))}function _n(n){switch(n?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return n?.language}}var ot=new Map;function b(n,e,t=1){const r=_n(e);const o=e?.number_format!=="none";const s=`${JSON.stringify(r)}|${t}|${o}`;let i=ot.get(s);if(!i){try{i=new Intl.NumberFormat(r,{minimumFractionDigits:t,maximumFractionDigits:t,useGrouping:o})}catch{i=new Intl.NumberFormat(void 0,{minimumFractionDigits:t,maximumFractionDigits:t})}ot.set(s,i)}return i.format(n)}function $e(n,e,t){return b(G(n,e),t)}function it(n,e,t){return b(vn(n,e),t)}var xn=2;var $n=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function at(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const e=n;if(e.schema_version!==xn){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(e.schema_version)}.`)}if(!e.plant||!Array.isArray(e.zones)||!Array.isArray(e.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return e}function lt(n){return[...n.alerts].sort((e,t)=>e.priority-t.priority||e.code.localeCompare(t.code)||e.scope.localeCompare(t.scope))}function ct(n){const e=n.plant.health.toLowerCase();const t=n.alerts.some(o=>o.severity==="critical"||o.severity==="error");if(n.safe_shutdown.active||t||["blocked","critical","error","failed","unhealthy"].includes(e)){return"attention"}const r=`${n.plant.active_mode} ${n.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function Se(n){return $n.has(n.toLowerCase())}function dt(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:n.thermostat.control_entity_id,temperature:e}}}function ut(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:n.thermostat.control_entity_id,preset_mode:e}}}function pt(n,e){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;if(!ke(n).includes(e))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:n.thermostat.control_entity_id,hvac_mode:e}}}function ht(n,e){if(!n.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:n.controls.requested_mode,option:e}}}function mt(n){if(!n.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:n.controls.safe_shutdown}}}function ft(n){const e=String(n.action??"operation").replaceAll("_"," ");const t=String(n.actuator_name??"actuator");const r=String(n.result??"");if(r==="proposed")return`Would ${e} ${t}`;if(r==="executed")return`Executed ${t} ${e}`;if(r==="suppressed")return`Suppressed ${t} ${e}`;return`${r||"Operation"}: ${t} ${e}`}function Sn(n){return n.replaceAll("_"," ")}function V(n,e,t){const[r,o]=e.split(".");return n?.(`component.hydronicus.entity.${r}.${o}.state.${t}`)||f(t)}function f(n){const e=Sn(n);return e.charAt(0).toUpperCase()+e.slice(1)}var wn={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function we(n,e){return n?.(`component.climate.entity_component._.state.${e}`)||wn[e]||f(e)}function ke(n){if(n.thermostat.kind!=="hydronicus")return[];return[...new Set(n.thermostat.hvac_modes??[])]}function Ce(n){if(n.dry_run||n.mode==="dry_run")return"Dry run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"Live";return f(n.mode)}function gt(n){if(n.dry_run||n.mode==="dry_run")return"dry-run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"live";return n.mode.replaceAll("_","-")}function bt(n){const{active_name:e,recommended_name:t}=n.plant.source;if(!n.sources.length&&!e&&!t)return null;const r=[e??"None active"];if(t&&t!==e)r.push(`recommended ${t}`);return r.join(" \xB7 ")}var kn={zone:"Room",circuit:"Loop"};var Cn={plant_initializing:"Starting",plant_unavailable:"Plant unavailable",binding_unavailable:"Entity unavailable",zone_sensor_blocked:"Sensor blocked",zone_mode_blocked:"Room blocked",cooling_blocked:"Cooling blocked",actuator_mismatch:"Equipment mismatch",actuator_blocked:"Equipment blocked",mode_changeover:"Mode changeover"};function yt(n){const e=Cn[n.code]??f(n.code);return n.scope!=="plant"&&n.name?`${n.name} \xB7 ${e}`:e}function Ae(n){return kn[n]??f(n)}function vt(n){return[...new Set(n.thermostat.preset_modes)].filter(e=>e!=="none")}function _t(n,e,t=P){if(n.thermostat.target_temperature===null)return null;return st(n.thermostat.target_temperature,e,t)}var An="hydronicus/subscribe_plant";var En=1e3;var Pn=6e4;var Rn={setTimeout:(n,e)=>globalThis.setTimeout(n,e),clearTimeout:n=>globalThis.clearTimeout(n)};var xt={plant_not_found:"not_found",unauthorized:"unauthorized"};function $t(n){return n!==void 0&&Object.hasOwn(xt,n)?xt[n]:void 0}function Tn(n){return typeof n==="object"&&n!==null&&"code"in n?String(n.code):void 0}function B(n,e){if(n instanceof Error)return n.message;if(typeof n==="object"&&n!==null&&"message"in n&&n.message){return String(n.message)}return e}function Ee(n){if(!n)return;try{void Promise.resolve(n()).catch(()=>void 0)}catch{}}var J=class{constructor(e,t=Rn){this.host=e;this.scheduler=t}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(e,t){if(e===this.connection&&t===this.plantId)return;this.disconnect();if(!e||!t)return;this.connection=e;this.plantId=t;e.addEventListener?.("disconnected",this.handleDisconnected);e.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;Ee(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const e=this.connection;const t=this.plantId;if(!e||!t)return;this.cancelRetry();const r=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}e.subscribeMessage(o=>this.handleEvent(r,o),{type:An,plant_id:t},{resubscribe:false}).then(o=>{if(r!==this.generation){Ee(o);return}this.unsubscribe=o}).catch(o=>{if(r!==this.generation)return;this.handleError(o)})}handleEvent(e,t){if(e!==this.generation)return;if(t.snapshot!==void 0&&t.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(t.snapshot);return}if(t.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const r=$t(t.status);if(r)this.stop({kind:r})}handleError(e){const t=$t(Tn(e));if(t){this.stop({kind:t});return}const r=Math.min(En*2**this.attempt,Pn);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:r,message:B(e,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},r)}stop(e){this.cancelRetry();this.generation+=1;Ee(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(e)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(e){this.current=e;this.host.onStatus(e)}};var M={status:{kind:"idle"},snapshot:null,snapshotError:null};var Hn=new Set(["idle","unavailable","not_found","unauthorized"]);var Pe=class{listeners=new Set;current=M;stream;constructor(e){this.stream=new J({onStatus:t=>this.statusChanged(t),onSnapshot:t=>this.snapshotReceived(t)},e)}get state(){return this.current}open(e,t){this.stream.connect(e,t)}close(){this.stream.disconnect()}statusChanged(e){const t=Hn.has(e.kind)?null:this.current.snapshot;this.publish({...this.current,status:e,snapshot:t})}snapshotReceived(e){try{this.publish({...this.current,snapshot:at(e),snapshotError:null})}catch(t){this.publish({...this.current,snapshot:null,snapshotError:B(t,"Unsupported Hydronicus snapshot.")})}}publish(e){this.current=e;for(const t of[...this.listeners])t(e)}};var Re=class{constructor(e){this.scheduler=e}scheduler;feeds=new WeakMap;subscribe(e,t,r){let o=this.feeds.get(e);if(!o){o=new Map;this.feeds.set(e,o)}let s=o.get(t);const i=!s;if(!s){s=new Pe(this.scheduler);o.set(t,s)}s.listeners.add(r);if(i)s.open(e,t);else r(s.state);const u=o;const l=s;let d=false;return()=>{if(d)return;d=true;l.listeners.delete(r);if(l.listeners.size)return;queueMicrotask(()=>{if(l.listeners.size||u.get(t)!==l)return;u.delete(t);l.close()})}}snapshot(e,t,r=2e3){return new Promise(o=>{let s=false;const i=d=>{if(s)return;s=true;clearTimeout(u);queueMicrotask(()=>l());o(d)};const u=setTimeout(()=>i(null),r);const l=this.subscribe(e,t,d=>{if(d.snapshot)i(d.snapshot);else if(["not_found","unauthorized"].includes(d.status.kind)||d.snapshotError)i(null)})})}};var St=new Re;var wt=ae`
  :host {
    display: block;
    --hydronicus-border: var(--divider-color, color-mix(in srgb, var(--primary-text-color, #1c1c1c) 13%, transparent));
    --hydronicus-muted: var(--secondary-text-color, #5f6368);
    --hydronicus-surface: var(--ha-card-background, var(--card-background-color, #fff));
    --hydronicus-raised: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 4%, transparent);
    --hydronicus-danger: var(--error-color, #db4437);
    --hydronicus-warning: var(--warning-color, #ffa600);
    --hydronicus-success: var(--success-color, #43a047);
    --hydronicus-accent: var(--primary-color, #03a9f4);
    --hydronicus-heating-color: var(--state-climate-heat-color, #ff8100);
    --hydronicus-cooling-color: var(--state-climate-cool-color, #2b9af9);
    --hydronicus-idle-color: var(--primary-color, #03a9f4);
    --hydronicus-attention-color: var(--error-color, #db4437);
    --hydronicus-glass-blur: 0px;
    --hydronicus-glass-opacity: 100%;
    --hydronicus-flow-duration: 2.2s;
    --hydronicus-ambient-duration: 16s;
    --hydronicus-state-color: var(--hydronicus-idle-color);
    --hydronicus-inline-start: left;
    --hydronicus-radius: var(--ha-border-radius-lg, 12px);
    font-variant-numeric: tabular-nums;
  }

  :host(:dir(rtl)) {
    --hydronicus-inline-start: right;
  }

  ha-card {
    display: block;
    box-sizing: border-box;
    container-type: inline-size;
    overflow: hidden;
    position: relative;
    isolation: isolate;
    height: 100%;
    color: var(--primary-text-color, #1c1c1c);
    background: color-mix(in srgb, var(--hydronicus-surface) var(--hydronicus-glass-opacity), transparent);
    -webkit-backdrop-filter: blur(var(--hydronicus-glass-blur));
    backdrop-filter: blur(var(--hydronicus-glass-blur));
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
      radial-gradient(circle at 18% 28%, color-mix(in srgb, var(--hydronicus-state-color) 16%, transparent) 0, transparent 32%),
      radial-gradient(circle at 82% 8%, color-mix(in srgb, var(--hydronicus-accent) 9%, transparent) 0, transparent 30%);
    opacity: 0.8;
    transform: translate3d(-2%, -1%, 0) scale(1.02);
    animation: hydronicus-ambient var(--hydronicus-ambient-duration) ease-in-out infinite alternate;
  }

  ha-card[data-visual="heating"] { --hydronicus-state-color: var(--hydronicus-heating-color); }
  ha-card[data-visual="cooling"] { --hydronicus-state-color: var(--hydronicus-cooling-color); }
  ha-card[data-visual="attention"] { --hydronicus-state-color: var(--hydronicus-attention-color); }
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
  h2 { font-size: var(--ha-font-size-xl, 1.25rem); font-weight: var(--ha-font-weight-medium, 500); line-height: 1.3; overflow-wrap: anywhere; }
  h3 { font-size: var(--ha-font-size-m, 0.95rem); font-weight: var(--ha-font-weight-medium, 500); }
  h4 { font-size: var(--ha-font-size-m, 0.9rem); font-weight: var(--ha-font-weight-medium, 500); }
  .muted, .meta { color: var(--hydronicus-muted); font-size: var(--ha-font-size-s, 0.8rem); line-height: 1.45; }
  .eyebrow { margin-block-end: 0.12rem; color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
  .plant-heading { align-items: flex-start; }
  .plant-mark {
    position: relative;
    flex: 0 0 2.7rem;
    inline-size: 2.7rem;
    block-size: 2.7rem;
    border-radius: var(--hydronicus-radius);
    background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent);
  }
  .plant-mark::before {
    content: "";
    position: absolute;
    inset: 0.58rem;
    border: 2px solid color-mix(in srgb, var(--hydronicus-state-color) 30%, transparent);
    border-block-start-color: var(--hydronicus-state-color);
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
    background: var(--hydronicus-state-color);
  }
  button.link {
    min-block-size: 0;
    border: 0;
    border-radius: 0.3rem;
    background: none;
    padding: 0;
    color: inherit;
    font: inherit;
    text-align: start;
    text-decoration: underline dotted color-mix(in srgb, currentColor 40%, transparent);
    text-underline-offset: 0.2em;
  }
  button.link:hover { background: none; text-decoration-color: currentColor; }
  .status-line { flex-wrap: wrap; margin-block-start: 0.48rem; gap: 0.35rem; }
  .status-primary { display: inline-flex; align-items: center; gap: 0.38rem; font-size: 0.86rem; font-weight: 600; }
  .status-dot { inline-size: 0.45rem; block-size: 0.45rem; border-radius: 50%; background: var(--hydronicus-state-color); animation: hydronicus-pulse 2.8s ease-out infinite; }
  .mode-detail { border-inline-start: 1px solid var(--hydronicus-border); padding-inline-start: 0.55rem; }
  .source-line { margin-block-start: 0.35rem; }
  .source-line strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
  .badge, .phase, .state { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.24rem 0.55rem; font-size: 0.72rem; line-height: 1.2; white-space: nowrap; }
  .badge { font-weight: 700; letter-spacing: 0.02em; background: color-mix(in srgb, var(--hydronicus-warning) 12%, transparent); }
  .badge.dry-run, .state.proposed { color: var(--hydronicus-warning); }
  .badge.mixed, .badge.live, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
  .badge.mixed, .badge.live { background: color-mix(in srgb, var(--hydronicus-danger) 10%, transparent); }
  .phase.off { color: var(--hydronicus-muted); }
  .badge.active, .state.active, .state.ready { color: var(--hydronicus-success); }
  .controls { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.45rem; }
  .mode-control { display: flex; align-items: center; min-block-size: 2.5rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); padding-inline-start: 0.62rem; }
  .control-label { color: var(--hydronicus-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  button, select { min-block-size: 2.5rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); color: inherit; font: inherit; padding: 0.38rem 0.7rem; transition: border-color 180ms ease, background-color 180ms ease, transform 120ms ease; }
  .mode-control select { border: 0; background: transparent; min-block-size: 2.4rem; }
  button { cursor: pointer; }
  button:hover, select:hover { border-color: color-mix(in srgb, var(--hydronicus-state-color) 46%, var(--hydronicus-border)); background: color-mix(in srgb, var(--primary-text-color, #1c1c1c) 8%, transparent); }
  button:active { transform: translateY(1px); }
  button:disabled, select:disabled { cursor: not-allowed; opacity: 0.5; }
  button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid var(--hydronicus-accent); outline-offset: 2px; }
  .shutdown { position: relative; overflow: hidden; color: var(--hydronicus-danger); touch-action: none; user-select: none; -webkit-user-select: none; }
  .shutdown.quiet { color: var(--hydronicus-muted); }
  .shutdown.quiet:hover, .shutdown.quiet:focus-visible, .shutdown.quiet.is-holding { color: var(--hydronicus-danger); }
  .shutdown::after { content: ""; position: absolute; inset: 0; z-index: 0; background: color-mix(in srgb, var(--hydronicus-danger) 18%, transparent); transform: scaleX(0); transform-origin: var(--hydronicus-inline-start); }
  .shutdown.is-holding::after { animation: hydronicus-hold 1.2s linear forwards; }
  .button-label { position: relative; z-index: 1; }
  .hold-progress { flex-basis: 100%; text-align: end; font-size: 0.7rem; color: var(--hydronicus-danger); }
  .alert, .error, .boundary, .notice { margin-block-start: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); padding: 0.68rem 0.75rem; }
  .alert, .notice, .action-error { position: relative; overflow: hidden; padding-inline-start: 0.9rem; }
  .alert::before, .notice::before, .action-error::before { content: ""; position: absolute; inset-block: 0; inset-inline-start: 0; inline-size: 3px; background: var(--hydronicus-warning); }
  .alert.error::before, .action-error::before { background: var(--hydronicus-danger); }
  .action-error { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-block-start: 0.9rem; border: 1px solid color-mix(in srgb, var(--hydronicus-danger) 40%, var(--hydronicus-border)); border-radius: var(--hydronicus-radius); padding-block: 0.4rem; padding-inline-end: 0.4rem; color: var(--hydronicus-danger); font-size: 0.85rem; }
  .action-error button { min-block-size: 2.2rem; color: inherit; }
  .boundary { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.65rem; }
  .boundary-orb { display: grid; place-items: center; inline-size: 1.75rem; block-size: 1.75rem; border-radius: 0.65rem; background: color-mix(in srgb, var(--hydronicus-state-color) 14%, transparent); color: var(--hydronicus-state-color); }
  .boundary-orb::before { content: ""; inline-size: 0.55rem; block-size: 0.55rem; border: 2px solid currentColor; border-radius: 50%; }
  .boundary-copy { min-inline-size: 0; align-items: baseline; flex-wrap: wrap; gap: 0.35rem; }
  .boundary-copy strong { font-size: 0.82rem; font-weight: 600; }
  section { margin-block-start: 1.05rem; }
  .section-head { justify-content: space-between; margin-block-end: 0.5rem; }
  .section-kicker { display: flex; align-items: center; gap: 0.42rem; }
  .section-kicker::before { content: ""; inline-size: 0.38rem; block-size: 0.38rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-state-color) 80%, transparent); }
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 245px), 1fr)); gap: 0.7rem; }
  .zone, .path, .actuator, details { border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); background: var(--hydronicus-raised); }
  .zone, .path, .actuator { padding: 0.72rem; }
  .zone { position: relative; overflow: hidden; transition: border-color 220ms ease, background-color 220ms ease; }
  .zone::before { content: ""; position: absolute; inset-block-start: 0; inset-inline: 0; block-size: 2px; background: var(--hydronicus-state-color); opacity: 0.18; transform: scaleX(0.35); transform-origin: var(--hydronicus-inline-start); transition: opacity 220ms ease, transform 380ms ease; }
  .zone[data-demand="true"]::before { opacity: 0.9; transform: scaleX(1); }
  .zone[data-demand="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 30%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 7%, transparent); }
  .zone[data-demand-kind="heating"] { --hydronicus-state-color: var(--hydronicus-heating-color); }
  .zone[data-demand-kind="cooling"] { --hydronicus-state-color: var(--hydronicus-cooling-color); }
  .zone[data-hvac-mode="off"] .metric.target { background: transparent; }
  .zone[data-blocked="true"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 34%, var(--hydronicus-border)); }
  .row { justify-content: space-between; align-items: baseline; }
  .zone-title { min-inline-size: 0; overflow-wrap: anywhere; }
  .zone-owner { margin-block-start: 0.12rem; }
  .temperature-panel { display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem; margin-block: 0.65rem 0.5rem; }
  .metric { min-inline-size: 0; border: 1px solid color-mix(in srgb, var(--hydronicus-border) 72%, transparent); border-radius: var(--hydronicus-radius); padding: 0.52rem 0.58rem; }
  .metric.target { background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
  .metric-value { font-size: clamp(1.22rem, 5cqi, 1.6rem); font-weight: 600; letter-spacing: -0.02em; }
  .metric-unit { margin-inline-start: 0.15rem; color: var(--hydronicus-muted); font-size: 0.75rem; }
  .metric-label { display: block; margin-block-start: 0.06rem; color: var(--hydronicus-muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .zone-note { margin-block-start: 0.28rem; }
  .diagnostic-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.45rem; }
  .diagnostic-chip { border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--hydronicus-muted); font-size: 0.7rem; }
  .diagnostic-chip.warning { color: var(--hydronicus-warning); border-color: color-mix(in srgb, var(--hydronicus-warning) 30%, var(--hydronicus-border)); }
  .diagnostic-chip.danger { color: var(--hydronicus-danger); border-color: color-mix(in srgb, var(--hydronicus-danger) 30%, var(--hydronicus-border)); }
  .coupling-note { display: inline-flex; align-items: center; gap: 0.3rem; margin-block-start: 0.38rem; color: color-mix(in srgb, var(--hydronicus-warning) 80%, var(--hydronicus-muted)); }
  .hvac-modes { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-block-start: 0.62rem; padding: 0.2rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); }
  .hvac-mode { flex: 1 1 auto; min-block-size: 2.2rem; padding-inline: 0.4rem; border-color: transparent; background: transparent; font-size: 0.8rem; white-space: nowrap; }
  .hvac-mode[aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-accent) 50%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-accent) 14%, transparent); font-weight: 600; }
  .hvac-mode[data-mode="heat"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-heating-color) 55%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-heating-color) 16%, transparent); }
  .hvac-mode[data-mode="cool"][aria-pressed="true"] { border-color: color-mix(in srgb, var(--hydronicus-cooling-color) 55%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-cooling-color) 16%, transparent); }
  .hvac-mode[data-mode="off"][aria-pressed="true"] { border-color: var(--hydronicus-border); background: var(--hydronicus-raised); }
  .zone-actions { display: flex; gap: 0.35rem; margin-block-start: 0.45rem; }
  .zone-actions button { min-inline-size: 2.75rem; }
  .preset { flex: 1; min-inline-size: 0; }
  .path-list, .actuator-list { display: grid; gap: 0.55rem; }
  .path { overflow: hidden; }
  .path-head { justify-content: space-between; flex-wrap: wrap; }
  .path-heading { display: flex; align-items: center; gap: 0.42rem; min-inline-size: 0; }
  .path-heading::before { content: ""; flex: 0 0 auto; inline-size: 0.43rem; block-size: 0.43rem; border-radius: 50%; background: color-mix(in srgb, var(--hydronicus-muted) 55%, transparent); }
  .path[data-flowing="true"] .path-heading::before { background: var(--hydronicus-state-color); animation: hydronicus-pulse 2.4s ease-out infinite; }
  .path[data-status="blocked"] .path-heading::before { background: var(--hydronicus-danger); }
  .path-track { display: flex; align-items: stretch; margin-block-start: 0.62rem; overflow-x: auto; overscroll-behavior-inline: contain; padding-block: 0.08rem 0.25rem; padding-inline: 0.03rem; scroll-snap-type: inline proximity; scrollbar-width: thin; }
  .path-step { display: contents; }
  .node { display: grid; align-content: start; flex: 0 0 clamp(5.4rem, 13cqi, 6.75rem); min-inline-size: 0; border: 1px solid var(--hydronicus-border); border-radius: calc(var(--hydronicus-radius) * 0.75); padding: 0.48rem 0.52rem; font-size: 0.76rem; overflow-wrap: anywhere; scroll-snap-align: start; transition: border-color 220ms ease, background-color 220ms ease; }
  .node[data-flowing="true"] { border-color: color-mix(in srgb, var(--hydronicus-state-color) 34%, var(--hydronicus-border)); background: color-mix(in srgb, var(--hydronicus-state-color) 8%, transparent); }
  .node[data-state="blocked"], .node[data-state="unavailable"] { border-color: color-mix(in srgb, var(--hydronicus-danger) 36%, var(--hydronicus-border)); }
  .node-kind { color: var(--hydronicus-muted); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .node-name { margin-block-start: 0.18rem; font-weight: 600; line-height: 1.25; }
  .node-state { display: flex; align-items: center; gap: 0.28rem; margin-block-start: 0.3rem; color: var(--hydronicus-muted); font-size: 0.68rem; }
  .node-state::before { content: ""; inline-size: 0.3rem; block-size: 0.3rem; border-radius: 50%; background: currentColor; }
  .node[data-flowing="true"] .node-state { color: color-mix(in srgb, var(--hydronicus-state-color) 78%, var(--primary-text-color, #1c1c1c)); }
  .flow-link { position: relative; flex: 1 0 clamp(1.2rem, 4cqi, 2.4rem); min-inline-size: 1.2rem; align-self: center; block-size: 2px; margin-inline: 0.12rem; overflow: hidden; background: color-mix(in srgb, var(--hydronicus-muted) 24%, transparent); }
  :host(:dir(rtl)) .flow-link { transform: scaleX(-1); }
  .flow-link::before { content: ""; position: absolute; inset-inline-end: 0; inset-block-start: 50%; inline-size: 0.34rem; block-size: 0.34rem; border-block-start: 1px solid var(--hydronicus-muted); border-inline-end: 1px solid var(--hydronicus-muted); transform: translateY(-50%) rotate(45deg); }
  .flow-link::after { content: ""; position: absolute; inset-block: -1px; inset-inline-start: 0; inline-size: 58%; background: linear-gradient(90deg, transparent, var(--hydronicus-state-color), transparent); opacity: 0; transform: translateX(-120%); }
  .path[data-flowing="true"] .flow-link { background: color-mix(in srgb, var(--hydronicus-state-color) 24%, transparent); }
  .path[data-flowing="true"] .flow-link::before { border-color: var(--hydronicus-state-color); }
  .path[data-flowing="true"] .flow-link::after { opacity: 0.95; animation: hydronicus-flow var(--hydronicus-flow-duration) linear infinite; }
  .path[data-status="blocked"] .flow-link { background: color-mix(in srgb, var(--hydronicus-danger) 30%, transparent); }
  .path-problem { margin-block-start: 0.5rem; color: var(--hydronicus-danger); }
  .actuator-list { grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
  .actuator-state { display: inline-flex; align-items: center; gap: 0.3rem; }
  .consumer-list { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-block-start: 0.48rem; }
  .consumer-chip { max-inline-size: 100%; border: 1px solid var(--hydronicus-border); border-radius: 999px; padding: 0.2rem 0.45rem; color: var(--hydronicus-muted); font-size: 0.7rem; overflow-wrap: anywhere; }
  .consumer-chip strong { color: var(--primary-text-color, #1c1c1c); font-weight: 600; }
  details { overflow: hidden; padding: 0.62rem 0.72rem; }
  details + details { margin-block-start: 0.45rem; }
  summary { cursor: pointer; font-size: 0.85rem; font-weight: 600; }
  details[open] summary { margin-block-end: 0.25rem; }
  details[open] .operation { animation: hydronicus-reveal 260ms ease both; }
  .operation { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.5rem; align-items: start; padding-block: 0.48rem; border-block-start: 1px solid var(--hydronicus-border); font-size: 0.82rem; }
  .operation:first-of-type { border-block-start: 0; }
  .operation-marker { inline-size: 0.4rem; block-size: 0.4rem; margin-block-start: 0.35rem; border-radius: 50%; background: var(--hydronicus-muted); }
  .operation[data-result="proposed"] .operation-marker { background: var(--hydronicus-warning); }
  .operation[data-result="executed"] .operation-marker { background: var(--hydronicus-success); }
  .operation[data-result="failed"] .operation-marker, .operation[data-result="timed_out"] .operation-marker { background: var(--hydronicus-danger); }
  .operation-copy { min-inline-size: 0; }
  .empty-state { padding: 0.8rem; border: 1px dashed var(--hydronicus-border); border-radius: var(--hydronicus-radius); text-align: center; }
  .state-card { display: grid; gap: 0.6rem; }
  .loading-card { min-block-size: 12rem; }
  .loading-head { display: flex; align-items: center; gap: 0.65rem; }
  .loading-mark, .skeleton { background: linear-gradient(105deg, var(--hydronicus-raised) 20%, color-mix(in srgb, var(--primary-text-color, #1c1c1c) 10%, transparent) 38%, var(--hydronicus-raised) 56%); background-size: 220% 100%; animation: hydronicus-shimmer 1.8s ease-in-out infinite; }
  .loading-mark { inline-size: 2.7rem; block-size: 2.7rem; border-radius: var(--hydronicus-radius); }
  .skeleton { inline-size: min(16rem, 62cqi); block-size: 0.72rem; border-radius: 999px; }
  .skeleton.short { inline-size: min(10rem, 42cqi); margin-block-start: 0.45rem; }
  .loading-panel { block-size: 4.2rem; margin-block-start: 0.9rem; border: 1px solid var(--hydronicus-border); border-radius: var(--hydronicus-radius); }
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
`;var zn=L("hassConnection");var Ln=L("hassApi");var Mn=L("hassConfig");var Un=L("hassInternationalization");var Q=class extends ${static properties={preview:{type:Boolean},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_plant:{state:true},_actionError:{state:true}};static styles=wt;_hass;_callService;_fromContext=new Set;_release;_followed;constructor(){super();this.preview=false;this._connection=void 0;this._unit=P;this._locale=void 0;this._localize=void 0;this._plant=M;this._actionError=null;new _(this,{context:zn,subscribe:true,callback:e=>{this._fromContext.add("connection");this._connection=e?.connection}});new _(this,{context:Ln,subscribe:true,callback:e=>{this._fromContext.add("api");this._callService=e?.callService}});new _(this,{context:Mn,subscribe:true,callback:e=>{this._fromContext.add("config");this._unit=_e(e?.config?.unit_system)}});new _(this,{context:Un,subscribe:true,callback:e=>{this._fromContext.add("i18n");this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}})}set hass(e){this._hass=e;if(!this._fromContext.has("connection"))this._connection=e?.connection;if(!this._fromContext.has("api"))this._callService=e?(...t)=>e.callService(...t):void 0;if(!this._fromContext.has("config"))this._unit=_e(e?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=e?.locale??(e?.language?{language:e.language}:void 0);this._localize=e?.localize}}get hass(){return this._hass}resetPlant(){this._plant=M;this._actionError=null}connectedCallback(){super.connectedCallback();this._follow()}disconnectedCallback(){this._unfollow();super.disconnectedCallback()}updated(e){super.updated(e);this._syncSelectValues();if(!this.isConnected)return;this._follow();if(this._connection&&(e.has("_connection")||this.preview))void U.load(this._connection)}_follow(){const e=this._connection;const t=this.plantId||void 0;const r=this._followed;if(r&&r.connection===e&&r.plantId===t)return;this._unfollow();if(!e||!t)return;this._followed={connection:e,plantId:t};this._release=St.subscribe(e,t,o=>{this._plant=o;this.plantStateChanged?.(o)})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._plant=M;this.plantStateChanged?.(M)}_syncSelectValues(){for(const e of this.renderRoot.querySelectorAll("select[data-value]")){const t=e.dataset.value??"";if(e.value!==t)e.value=t}}get renderContext(){return{unit:this._unit,locale:this._locale,localize:this._localize,moreInfo:e=>this.moreInfo(e),call:e=>this.call(e)}}moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:e}}))}call(e){const t=this._callService;if(!e||!t)return;t(e.domain,e.service,e.data,void 0,false).then(()=>{this._actionError=null},r=>{this._actionError=B(r,"The Home Assistant action failed.");this.requestUpdate()})}dismissActionError=()=>{this._actionError=null}};function kt(n,e,t,r){const o=n.unit;if(e===null){return a`<div class=${r}><span class="metric-value">--</span><span class="metric-label">${t}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${r}><span class="metric-value">${$e(e,o,n.locale)}</span><span class="metric-unit">${o}</span><span class="metric-label">${t}</span></div>`}function Ct(n,e,t){const r=_t(e,t,n.unit);if(r!==null)n.call(dt(e,r))}function qn(n,e,t){if(t===e.thermostat.hvac_mode)return;n.call(pt(e,t))}function Nn(n,e,t){n.call(ut(e,t.target.value))}function At(n,e,t){const r=e.thermostat;const o=r.kind==="hydronicus";const s=e.cooling.demand?"cooling":e.demand?"heating":"none";const i=s!=="none";const u=r.hvac_mode==="off";const{unit:l,locale:d,localize:h}=n;const p=b(xe(l),d,l===P?1:0);const m=r.control_entity_id;const g=Boolean(m)&&r.target_temperature!==null;const S=vt(e);const ze=ke(e);const te=r.hvac_mode?we(h,r.hvac_mode):null;const jt=u&&!e.blocked?te??"Off":f(e.phase);const Le=i?`${s==="cooling"?"Cooling":"Heating"} demand active`:u?"Thermostat off":"No demand";const ne=`zone-${e.id}`;const Me=m?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>n.moreInfo(m)}>${e.name}</button>`:e.name;const Vt=t.headingLevel===2?a`<h2 class="zone-title" id=${ne}>${Me}</h2>`:a`<h4 class="zone-title" id=${ne}>${Me}</h4>`;return a`<article class="zone" data-phase=${e.phase} data-hvac-mode=${r.hvac_mode??"unknown"} data-demand=${String(i)} data-demand-kind=${s} data-blocked=${String(e.blocked)} aria-labelledby=${ne}>
    <div class="row"><div>${Vt}<p class="meta zone-owner">${o?"Hydronicus thermostat":`External thermostat \xB7 read-only${te?` \xB7 ${te}`:""}`}</p></div><span class=${`phase${e.blocked?" state blocked":""}${u?" off":""}`}>${jt}</span></div>
    <div class="temperature-panel">
      ${kt(n,r.current_temperature,"Current","metric")}
      ${kt(n,r.target_temperature,"Target","metric target")}
    </div>
    <p class="meta zone-note" dir="auto">${o?Le:`${Le} \xB7 ${r.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Room diagnostics">
      <li class="diagnostic-chip" dir="auto">${b(e.sensor_status.usable,d,0)} sensor${e.sensor_status.usable===1?"":"s"} ready</li>
      ${e.sensor_status.optional_excluded?a`<li class="diagnostic-chip warning" dir="auto">${b(e.sensor_status.optional_excluded,d,0)} optional excluded</li>`:c}
      ${e.sensor_status.required_blocking?a`<li class="diagnostic-chip danger" dir="auto">${b(e.sensor_status.required_blocking,d,0)} required blocked</li>`:c}
      ${e.cooling.dew_point===null?c:a`<li class="diagnostic-chip" dir="auto">Dew point ${$e(e.cooling.dew_point,l,d)} ${l}</li>`}
      ${e.cooling.condensation_margin===null?c:a`<li class="diagnostic-chip ${e.cooling.blocked?"danger":""}" dir="auto">Margin ${it(e.cooling.condensation_margin,l,d)} ${l}</li>`}
    </ul>
    ${r.preset&&r.preset!=="none"?a`<p class="meta zone-note" dir="auto">Preset: ${f(r.preset)}</p>`:c}
    ${e.blocked_reason?a`<p class="meta zone-note" dir="auto">${e.blocked_reason}</p>`:c}
    ${e.coupling_group_ids.length?a`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>`:c}
    ${o?a`${ze.length?a`<div class="hvac-modes" role="group" aria-label=${`${e.name} HVAC mode`}>${ze.map(y=>a`<button type="button" class="hvac-mode" data-mode=${y} aria-pressed=${String(y===r.hvac_mode)} ?disabled=${!m} @click=${()=>qn(n,e,y)}>${we(h,y)}</button>`)}</div>`:c}
          <div class="zone-actions">
            <button type="button" dir="ltr" ?disabled=${!g} aria-label=${`Decrease ${e.name} target by ${p} ${l}`} @click=${()=>Ct(n,e,-1)}>−${p}</button>
            <button type="button" dir="ltr" ?disabled=${!g} aria-label=${`Increase ${e.name} target by ${p} ${l}`} @click=${()=>Ct(n,e,1)}>+${p}</button>
            ${S.length?a`<select class="preset" data-value=${r.preset??"none"} aria-label=${`${e.name} preset`} ?disabled=${!m} @change=${y=>Nn(n,e,y)}>${["none",...S].map(y=>a`<option value=${y}>${f(y)}</option>`)}</select>`:c}
          </div>`:a`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`}var Te=["auto","idle","heating","cooling"];function On(n,e){const t=e.plant;const r=`Mode ${V(n.localize,"select.requested_mode",t.requested_mode)}`;if(t.requested_mode==="auto"||t.requested_mode===t.active_mode)return r;return`${r} \xB7 now ${V(n.localize,"sensor.operating_mode",t.active_mode)}`}function Et(n,e,t){const r=e.plant;const o=r.execution_boundary;const s=e.controls.requested_mode;const i=Te.includes(r.requested_mode)?Te:[...Te,r.requested_mode];const u=bt(e);const l=d=>n.call(ht(e,d.target.value));return a`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${s?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>n.moreInfo(s)}>${r.name}</button>`:r.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${V(n.localize,"sensor.controller_status",r.status)}</span>
            <span class="meta mode-detail">${On(n,e)}</span>
          </div>
          ${u===null?c:a`<p class="meta source-line" dir="auto"><strong>Source</strong> ${u}</p>`}
          <p class="meta" dir="auto">${r.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${gt(o)}"><span class="visually-hidden">Execution boundary: </span>${Ce(o)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${r.requested_mode} ?disabled=${!s} @change=${l}>
          ${i.map(d=>a`<option value=${d}>${V(n.localize,"select.requested_mode",d)}</option>`)}
        </select></label>
        ${t}
      </div>
    </header>`}function Pt(n){return a`<div class="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${n.plant.execution_boundary.message||`${Ce(n.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`}function Rt(n,e){const t=lt(e);if(!t.length)return c;return a`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${b(t.length,n.locale,0)}</span></div>${t.slice(0,3).map(r=>{const o=r.severity==="error"||r.severity==="critical";return a`<p class="alert ${o?"error":""}" data-severity=${r.severity} dir="auto"><strong>${yt(r)}</strong><span> · ${r.message}</span></p>`})}</section>`}function Tt(n,e){return a`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${b(e.zones.length,n.locale,0)} visible</span></div><div class="zone-grid">${e.zones.length?e.zones.map(t=>At(n,t,{headingLevel:4})):a`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`}function Ht(n){if(!n.delivery_paths.length)return c;return a`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${n.delivery_paths.map(e=>a`<article class="path" data-status=${e.status} data-flowing=${String(Se(e.status))}>
    <div class="path-head"><div class="path-heading"><strong>${n.zones.find(t=>t.id===e.zone_id)?.name??e.zone_id}</strong></div><div class="status-line"><span class="state ${e.status}">${f(e.status)}</span>${e.coupled?a`<span class="meta">shares equipment</span>`:c}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${e.nodes.map((t,r)=>a`<li class="path-step">${r?a`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" data-kind=${t.kind} data-state=${t.state} data-flowing=${String(Se(t.state))}><span class="node-kind">${Ae(t.kind)}</span><span class="node-name">${t.name}</span><span class="node-state">${f(t.state)}</span></span></li>`)}</ol>
    ${e.problem?a`<p class="meta path-problem" dir="auto">${e.problem}</p>`:c}
  </article>`)}</div></section>`}function zt(n){if(!n.actuators.length)return c;return a`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${n.actuators.map(e=>a`<article class="actuator" data-state=${e.state}><div class="row"><strong>${e.name}</strong><span class="state actuator-state ${e.state}">${f(e.state)}</span></div><p class="meta" dir="auto">${f(e.kind)} · ${e.reason??"No additional explanation."}</p>${e.active_consumers.length?a`<ul class="consumer-list" aria-label="Loops using this equipment">${e.active_consumers.map(t=>a`<li class="consumer-chip" title=${t.id}><strong>${t.name}</strong></li>`)}</ul>`:a`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}function Lt(n){return a`<section><details><summary>Controller explanations</summary>${n.explanations.map(e=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${e.name??Ae(e.scope)}</strong> · ${e.message}</p></div>`)}</details></section>`}function Mt(n,e){const t=Object.values(e.execution.operations).flat();if(!t.length)return c;return a`<section><details open><summary>Latest operation outcomes (${b(t.length,n.locale,0)})</summary>${t.map(r=>{const o=String(r.result??"unknown");return a`<div class="operation" data-result=${o}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${ft(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}function Ut(n){return`Retrying in ${Math.round(n/1e3)} s.`}function R(n,e,t,r,o){return a`<ha-card class="state-card" data-visual=${r==="alert"?"attention":"idle"}>
    <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">${n}</p><h2>${e}</h2></div></div>
    <p class=${r==="alert"?"notice error":"notice"} role=${r} dir="auto">${t}</p>
    ${o?a`<p class="meta" dir="auto">${o}</p>`:c}
  </ha-card>`}function Dn(n){return a`<ha-card class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${n?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
  </ha-card>`}function qt(n){return n.snapshotError?null:n.snapshot}function Nt(n,e){if(e.snapshotError){return R(n,"Card update needed",e.snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const t=e.status;switch(t.kind){case"not_found":return R(n,"Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return R(n,"No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return R(n,"Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return R(n,"Connection needs attention",t.message,"alert",Ut(t.delayMs));default:return Dn(t.kind==="reconnecting")}}function Ot(n){if(n.kind==="reconnecting"){return a`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(n.kind==="retrying"){return a`<p class="notice" role="status" dir="auto">${n.message} ${Ut(n.delayMs)} The values below may be out of date.</p>`}return c}function Dt(n,e){if(!n)return c;return a`<div class="action-error" role="alert"><span dir="auto">${n}</span><button type="button" @click=${e}>Dismiss</button></div>`}var In=1200;var He="Hydronicus Plant";var Fn=["rooms","paths","equipment"];function jn(n,e){switch(n){case"header":return 4;case"alerts":{const t=Math.min(e.alerts.length,3);return t?1+t:0}case"rooms":return 1+Math.max(1,e.zones.length)*5;case"paths":return e.delivery_paths.length?1+e.delivery_paths.length*3:0;case"equipment":return e.actuators.length?1+e.actuators.length*2:0;case"explanations":return 1;case"operations":{const t=Object.values(e.execution.operations).flat().length;return t?1+t:0}}}var ee=class extends Q{static properties={_config:{state:true},_holdingShutdown:{state:true}};_holdTimer=null;constructor(){super();this._config=void 0;this._holdingShutdown=false}static async getConfigForm(){return Oe()}static async getStubConfig(e){return Ne(e)}setConfig(e){const t=se(e);if(t.plant!==this._config?.plant)this.resetPlant();this._config=t}get plantId(){return this._config?.plant}getCardSize(){const e=this._plant.snapshot;const t=W(this._config);if(!e)return t.includes("header")?4:2;return Math.max(1,t.reduce((r,o)=>r+jn(o,e),0))}getGridOptions(){const e=W(this._config).some(t=>Fn.includes(t));return e?{columns:12,min_columns:6}:{columns:6,min_columns:4}}disconnectedCallback(){this._clearHold();super.disconnectedCallback()}plantStateChanged(e){if(!e.snapshot)this._clearHold()}render(){const e=this._config;if(!e||!e.plant){return R(He,He,"Select a Hydronicus Plant in the card editor.","status")}const t=this._plant;const r=qt(t);if(!r)return Nt(He,t);const o=this.renderContext;const s=W(e);const i=a`${Ot(t.status)}${Dt(this._actionError,this.dismissActionError)}`;return a`<ha-card class=${e.density??"comfortable"} data-visual=${ct(r)}>
      ${s.includes("header")?c:i}
      ${s.map(u=>this._renderSection(u,o,r,i))}
    </ha-card>`}_renderSection(e,t,r,o){switch(e){case"header":return a`${Et(t,r,this._renderShutdown(r))}
          ${o}
          ${Pt(r)}`;case"alerts":return Rt(t,r);case"rooms":return Tt(t,r);case"paths":return Ht(r);case"equipment":return zt(r);case"explanations":return Lt(r);case"operations":return Mt(t,r)}}_renderShutdown(e){const t=!e.controls.safe_shutdown;const r=e.plant.execution_boundary.dry_run;return a`<button type="button" class=${`shutdown${r?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${t} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_startHold(){if(!this._plant.snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;const e=this._plant.snapshot;if(e)this.call(mt(e))},In)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=e=>{if(e.button!==void 0&&e.button>0)return;this._startHold()};_keyHoldStart=e=>{if(e.key!=="Enter"&&e.key!==" ")return;e.preventDefault();if(!e.repeat)this._startHold()};_keyHoldEnd=e=>{if(e.key==="Enter"||e.key===" ")this._clearHold()};_preventContextMenu=e=>{e.preventDefault()}};function It(n){if(!n.get(T))n.define(T,ee)}var Ft=window.customElements;It(Ft);void Ft.whenDefined("home-assistant").then(()=>{It(window.customElements)});window.customCards=window.customCards??[];if(!window.customCards.some(n=>n.type===T)){window.customCards.push({type:T,name:"Hydronicus Plant",version:"0.1.0-rc.6",description:"Topology-driven Hydronicus Plant status and controls.",preview:true,documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
