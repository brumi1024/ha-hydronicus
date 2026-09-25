var T="hydronicus-plant-card";var nt=`custom:${T}`;var Fe="hydronicus/list_plants";var je=["comfortable","compact"];function ot(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus Plant card requires a configuration.")}const t=n;if(t.type!==nt){throw new Error(`Hydronicus Plant card type must be ${nt}.`)}if(typeof t.plant!=="string"){throw new Error("Hydronicus Plant card requires one Plant UUID in `plant`.")}const e=t.density??"comfortable";if(!je.includes(e)){throw new Error("Hydronicus Plant card density must be comfortable or compact.")}return{type:nt,plant:t.plant.trim(),density:e}}var rt=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(t){if(this.connection===t&&this.pending)return this.pending;this.connection=t;this.pending=t.sendMessagePromise({type:Fe}).then(e=>{this.plants=Array.isArray(e.plants)?e.plants:[];return this.plants}).catch(()=>{if(this.connection===t)this.pending=null;return this.plants});return this.pending}async settled(t=2e3){if(!this.pending)return this.plants;let e;const r=new Promise(o=>{e=setTimeout(()=>o(this.plants),t)});try{return await Promise.race([this.pending,r])}finally{clearTimeout(e)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var U=new rt;async function Mt(n){const t=n?.connection?await U.load(n.connection):U.known;return{plant:t[0]?.id??"",density:"comfortable"}}var Ve={plant:"Hydronicus Plant",density:"Density"};var Be={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",density:"Compact uses less spacing for dense dashboards."};function We(n){if(n.length===0)return{text:{}};return{select:{mode:"dropdown",options:n.map(t=>({value:t.id,label:t.name}))}}}async function Ut(){const n=await U.settled();return{schema:[{name:"plant",required:true,selector:We(n)},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}}],computeLabel:t=>Ve[t.name],computeHelper:t=>Be[t.name],assertConfig:t=>{ot(t)}}}var W=globalThis;var K=W.ShadowRoot&&(void 0===W.ShadyCSS||W.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var st=Symbol();var qt=new WeakMap;var q=class{constructor(t,e,r){if(this._$cssResult$=true,r!==st)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(K&&void 0===t){const r=void 0!==e&&1===e.length;r&&(t=qt.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),r&&qt.set(e,t))}return t}toString(){return this.cssText}};var Nt=n=>new q("string"==typeof n?n:n+"",void 0,st);var it=(n,...t)=>{const e=1===n.length?n[0]:t.reduce((r,o,s)=>r+(i=>{if(true===i._$cssResult$)return i.cssText;if("number"==typeof i)return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[s+1],n[0]);return new q(e,n,st)};var Ot=(n,t)=>{if(K)n.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const e of t){const r=document.createElement("style"),o=W.litNonce;void 0!==o&&r.setAttribute("nonce",o),r.textContent=e.cssText,n.appendChild(r)}};var at=K?n=>n:n=>n instanceof CSSStyleSheet?(t=>{let e="";for(const r of t.cssRules)e+=r.cssText;return Nt(e)})(n):n;var{is:Ke,defineProperty:Xe,getOwnPropertyDescriptor:Ze,getOwnPropertyNames:Ye,getOwnPropertySymbols:Ge,getPrototypeOf:Je}=Object;var X=globalThis;var Dt=X.trustedTypes;var Qe=Dt?Dt.emptyScript:"";var tn=X.reactiveElementPolyfillSupport;var N=(n,t)=>n;var lt={toAttribute(n,t){switch(t){case Boolean:n=n?Qe:null;break;case Object:case Array:n=null==n?n:JSON.stringify(n)}return n},fromAttribute(n,t){let e=n;switch(t){case Boolean:e=null!==n;break;case Number:e=null===n?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch(r){e=null}}return e}};var Ft=(n,t)=>!Ke(n,t);var It={attribute:true,type:String,converter:lt,reflect:false,useDefault:false,hasChanged:Ft};Symbol.metadata??=Symbol("metadata"),X.litPropertyMetadata??=new WeakMap;var v=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=It){if(e.state&&(e.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=true),this.elementProperties.set(t,e),!e.noAccessor){const r=Symbol(),o=this.getPropertyDescriptor(t,r,e);void 0!==o&&Xe(this.prototype,t,o)}}static getPropertyDescriptor(t,e,r){const{get:o,set:s}=Ze(this.prototype,t)??{get(){return this[e]},set(i){this[e]=i}};return{get:o,set(i){const u=o?.call(this);s?.call(this,i),this.requestUpdate(t,u,r)},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??It}static _$Ei(){if(this.hasOwnProperty(N("elementProperties")))return;const t=Je(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(N("properties"))){const e=this.properties,r=[...Ye(e),...Ge(e)];for(const o of r)this.createProperty(o,e[o])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[r,o]of e)this.elementProperties.set(r,o)}this._$Eh=new Map;for(const[e,r]of this.elementProperties){const o=this._$Eu(e,r);void 0!==o&&this._$Eh.set(o,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const r=new Set(t.flat(1/0).reverse());for(const o of r)e.unshift(at(o))}else void 0!==t&&e.push(at(t));return e}static _$Eu(t,e){const r=e.attribute;return false===r?void 0:"string"==typeof r?r:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const r of e.keys())this.hasOwnProperty(r)&&(t.set(r,this[r]),delete this[r]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ot(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,r){this._$AK(t,r)}_$ET(t,e){const r=this.constructor.elementProperties.get(t),o=this.constructor._$Eu(t,r);if(void 0!==o&&true===r.reflect){const s=(void 0!==r.converter?.toAttribute?r.converter:lt).toAttribute(e,r.type);this._$Em=t,null==s?this.removeAttribute(o):this.setAttribute(o,s),this._$Em=null}}_$AK(t,e){const r=this.constructor,o=r._$Eh.get(t);if(void 0!==o&&this._$Em!==o){const s=r.getPropertyOptions(o),i="function"==typeof s.converter?{fromAttribute:s.converter}:void 0!==s.converter?.fromAttribute?s.converter:lt;this._$Em=o;const u=i.fromAttribute(e,s.type);this[o]=u??this._$Ej?.get(o)??u,this._$Em=null}}requestUpdate(t,e,r,o=false,s){if(void 0!==t){const i=this.constructor;if(false===o&&(s=this[t]),r??=i.getPropertyOptions(t),!((r.hasChanged??Ft)(s,e)||r.useDefault&&r.reflect&&s===this._$Ej?.get(t)&&!this.hasAttribute(i._$Eu(t,r))))return;this.C(t,e,r)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:r,reflect:o,wrapped:s},i){r&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,i??e??this[t]),true!==s||void 0!==i)||(this._$AL.has(t)||(this.hasUpdated||r||(e=void 0),this._$AL.set(t,e)),true===o&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(e){Promise.reject(e)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[o,s]of this._$Ep)this[o]=s;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[o,s]of r){const{wrapped:i}=s,u=this[o];true!==i||this._$AL.has(o)||void 0===u||this.C(o,void 0,s,u)}}let t=false;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(e)):this._$EM()}catch(r){throw t=false,this._$EM(),r}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return true}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[N("elementProperties")]=new Map,v[N("finalized")]=new Map,tn?.({ReactiveElement:v}),(X.reactiveElementVersions??=[]).push("2.1.2");var gt=globalThis;var jt=n=>n;var Z=gt.trustedTypes;var Vt=Z?Z.createPolicy("lit-html",{createHTML:n=>n}):void 0;var Yt="$lit$";var x=`lit$${Math.random().toFixed(9).slice(2)}$`;var Gt="?"+x;var en=`<${Gt}>`;var C=document;var D=()=>C.createComment("");var I=n=>null===n||"object"!=typeof n&&"function"!=typeof n;var ft=Array.isArray;var nn=n=>ft(n)||"function"==typeof n?.[Symbol.iterator];var ct="[ 	\n\f\r]";var O=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Bt=/-->/g;var Wt=/>/g;var S=RegExp(`>|${ct}(?:([^\\s"'>=/]+)(${ct}*=${ct}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Kt=/'/g;var Xt=/"/g;var Jt=/^(?:script|style|textarea|title)$/i;var bt=n=>(t,...e)=>({_$litType$:n,strings:t,values:e});var a=bt(1);var Nn=bt(2);var On=bt(3);var A=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var Zt=new WeakMap;var w=C.createTreeWalker(C,129);function Qt(n,t){if(!ft(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Vt?Vt.createHTML(t):t}var rn=(n,t)=>{const e=n.length-1,r=[];let o,s=2===t?"<svg>":3===t?"<math>":"",i=O;for(let u=0;u<e;u++){const l=n[u];let d,p,h=-1,m=0;for(;m<l.length&&(i.lastIndex=m,p=i.exec(l),null!==p);)m=i.lastIndex,i===O?"!--"===p[1]?i=Bt:void 0!==p[1]?i=Wt:void 0!==p[2]?(Jt.test(p[2])&&(o=RegExp("</"+p[2],"g")),i=S):void 0!==p[3]&&(i=S):i===S?">"===p[0]?(i=o??O,h=-1):void 0===p[1]?h=-2:(h=i.lastIndex-p[2].length,d=p[1],i=void 0===p[3]?S:'"'===p[3]?Xt:Kt):i===Xt||i===Kt?i=S:i===Bt||i===Wt?i=O:(i=S,o=void 0);const f=i===S&&n[u+1].startsWith("/>")?" ":"";s+=i===O?l+en:h>=0?(r.push(d),l.slice(0,h)+Yt+l.slice(h)+x+f):l+x+(-2===h?u:f)}return[Qt(n,s+(n[e]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),r]};var F=class n{constructor({strings:t,_$litType$:e},r){let o;this.parts=[];let s=0,i=0;const u=t.length-1,l=this.parts,[d,p]=rn(t,e);if(this.el=n.createElement(d,r),w.currentNode=this.el.content,2===e||3===e){const h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;null!==(o=w.nextNode())&&l.length<u;){if(1===o.nodeType){if(o.hasAttributes())for(const h of o.getAttributeNames())if(h.endsWith(Yt)){const m=p[i++],f=o.getAttribute(h).split(x),k=/([.?@])?(.*)/.exec(m);l.push({type:1,index:s,name:k[2],strings:f,ctor:"."===k[1]?ut:"?"===k[1]?ht:"@"===k[1]?pt:z}),o.removeAttribute(h)}else h.startsWith(x)&&(l.push({type:6,index:s}),o.removeAttribute(h));if(Jt.test(o.tagName)){const h=o.textContent.split(x),m=h.length-1;if(m>0){o.textContent=Z?Z.emptyScript:"";for(let f=0;f<m;f++)o.append(h[f],D()),w.nextNode(),l.push({type:2,index:++s});o.append(h[m],D())}}}else if(8===o.nodeType)if(o.data===Gt)l.push({type:2,index:s});else{let h=-1;for(;-1!==(h=o.data.indexOf(x,h+1));)l.push({type:7,index:s}),h+=x.length-1}s++}}static createElement(t,e){const r=C.createElement("template");return r.innerHTML=t,r}};function H(n,t,e=n,r){if(t===A)return t;let o=void 0!==r?e._$Co?.[r]:e._$Cl;const s=I(t)?void 0:t._$litDirective$;return o?.constructor!==s&&(o?._$AO?.(false),void 0===s?o=void 0:(o=new s(n),o._$AT(n,e,r)),void 0!==r?(e._$Co??=[])[r]=o:e._$Cl=o),void 0!==o&&(t=H(n,o._$AS(n,t.values),o,r)),t}var dt=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:r}=this._$AD,o=(t?.creationScope??C).importNode(e,true);w.currentNode=o;let s=w.nextNode(),i=0,u=0,l=r[0];for(;void 0!==l;){if(i===l.index){let d;2===l.type?d=new j(s,s.nextSibling,this,t):1===l.type?d=new l.ctor(s,l.name,l.strings,this,t):6===l.type&&(d=new mt(s,this,t)),this._$AV.push(d),l=r[++u]}i!==l?.index&&(s=w.nextNode(),i++)}return w.currentNode=C,o}p(t){let e=0;for(const r of this._$AV)void 0!==r&&(void 0!==r.strings?(r._$AI(t,r,e),e+=r.strings.length-2):r._$AI(t[e])),e++}};var j=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,r,o){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??true}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=H(this,t,e),I(t)?t===c||null==t||""===t?(this._$AH!==c&&this._$AR(),this._$AH=c):t!==this._$AH&&t!==A&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):nn(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==c&&I(this._$AH)?this._$AA.nextSibling.data=t:this.T(C.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:r}=t,o="number"==typeof r?this._$AC(t):(void 0===r.el&&(r.el=F.createElement(Qt(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(e);else{const s=new dt(o,this),i=s.u(this.options);s.p(e),this.T(i),this._$AH=s}}_$AC(t){let e=Zt.get(t.strings);return void 0===e&&Zt.set(t.strings,e=new F(t)),e}k(t){ft(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let r,o=0;for(const s of t)o===e.length?e.push(r=new n(this.O(D()),this.O(D()),this,this.options)):r=e[o],r._$AI(s),o++;o<e.length&&(this._$AR(r&&r._$AB.nextSibling,o),e.length=o)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(false,true,e);t!==this._$AB;){const r=jt(t).nextSibling;jt(t).remove(),t=r}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}};var z=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,r,o,s){this.type=1,this._$AH=c,this._$AN=void 0,this.element=t,this.name=e,this._$AM=o,this.options=s,r.length>2||""!==r[0]||""!==r[1]?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=c}_$AI(t,e=this,r,o){const s=this.strings;let i=false;if(void 0===s)t=H(this,t,e,0),i=!I(t)||t!==this._$AH&&t!==A,i&&(this._$AH=t);else{const u=t;let l,d;for(t=s[0],l=0;l<s.length-1;l++)d=H(this,u[r+l],e,l),d===A&&(d=this._$AH[l]),i||=!I(d)||d!==this._$AH[l],d===c?t=c:t!==c&&(t+=(d??"")+s[l+1]),this._$AH[l]=d}i&&!o&&this.j(t)}j(t){t===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}};var ut=class extends z{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===c?void 0:t}};var ht=class extends z{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==c)}};var pt=class extends z{constructor(t,e,r,o,s){super(t,e,r,o,s),this.type=5}_$AI(t,e=this){if((t=H(this,t,e,0)??c)===A)return;const r=this._$AH,o=t===c&&r!==c||t.capture!==r.capture||t.once!==r.once||t.passive!==r.passive,s=t!==c&&(r===c||o);o&&this.element.removeEventListener(this.name,this,r),s&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}};var mt=class{constructor(t,e,r){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(t){H(this,t)}};var on=gt.litHtmlPolyfillSupport;on?.(F,j),(gt.litHtmlVersions??=[]).push("3.3.3");var te=(n,t,e)=>{const r=e?.renderBefore??t;let o=r._$litPart$;if(void 0===o){const s=e?.renderBefore??null;r._$litPart$=o=new j(t.insertBefore(D(),s),s,void 0,e??{})}return o._$AI(n),o};var yt=globalThis;var $=class extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=te(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return A}};$._$litElement$=true,$["finalized"]=true,yt.litElementHydrateSupport?.({LitElement:$});var sn=yt.litElementPolyfillSupport;sn?.({LitElement:$});(yt.litElementVersions??=[]).push("4.2.2");var E=class extends Event{constructor(t,e,r,o){super("context-request",{bubbles:true,composed:true}),this.context=t,this.contextTarget=e,this.callback=r,this.subscribe=o??false}};function L(n){return n}var _=class{constructor(t,e,r,o){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(s,i)=>{this.unsubscribe&&(this.unsubscribe!==i&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=s,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(s,i)),this.unsubscribe=i},this.host=t,void 0!==e.context){const s=e;this.context=s.context,this.callback=s.callback,this.subscribe=s.subscribe??false}else this.context=e,this.callback=r,this.subscribe=o??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new E(this.context,this.host,this.t,this.subscribe))}};var P="\xB0C";var ln=5;var cn=35;function vt(n){return n?.temperature==="\xB0F"?"\xB0F":P}function Y(n,t){return t==="\xB0F"?n*9/5+32:n}function dn(n,t){return t==="\xB0F"?n*9/5:n}function _t(n){return n==="\xB0F"?1:.5}function ne(n,t,e){const r=_t(e);const o=Y(n,e);const s=o/r;const i=(t>0?Math.floor(s+1e-9)+1:Math.ceil(s-1e-9)-1)*r;const u=Y(ln,e);const l=Y(cn,e);return Number(Math.min(l,Math.max(u,i)).toFixed(1))}function un(n){switch(n?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return n?.language}}var ee=new Map;function b(n,t,e=1){const r=un(t);const o=t?.number_format!=="none";const s=`${JSON.stringify(r)}|${e}|${o}`;let i=ee.get(s);if(!i){try{i=new Intl.NumberFormat(r,{minimumFractionDigits:e,maximumFractionDigits:e,useGrouping:o})}catch{i=new Intl.NumberFormat(void 0,{minimumFractionDigits:e,maximumFractionDigits:e})}ee.set(s,i)}return i.format(n)}function xt(n,t,e){return b(Y(n,t),e)}function re(n,t,e){return b(dn(n,t),e)}var hn=2;var pn=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function oe(n){if(!n||typeof n!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const t=n;if(t.schema_version!==hn){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(t.schema_version)}.`)}if(!t.plant||!Array.isArray(t.zones)||!Array.isArray(t.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return t}function se(n){return[...n.alerts].sort((t,e)=>t.priority-e.priority||t.code.localeCompare(e.code)||t.scope.localeCompare(e.scope))}function ie(n){const t=n.plant.health.toLowerCase();const e=n.alerts.some(o=>o.severity==="critical"||o.severity==="error");if(n.safe_shutdown.active||e||["blocked","critical","error","failed","unhealthy"].includes(t)){return"attention"}const r=`${n.plant.active_mode} ${n.plant.status}`.toLowerCase();if(r.includes("cool"))return"cooling";if(r.includes("heat"))return"heating";return"idle"}function $t(n){return pn.has(n.toLowerCase())}function ae(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:n.thermostat.control_entity_id,temperature:t}}}function le(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:n.thermostat.control_entity_id,preset_mode:t}}}function ce(n,t){if(n.thermostat.kind!=="hydronicus"||!n.thermostat.control_entity_id)return null;if(!St(n).includes(t))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:n.thermostat.control_entity_id,hvac_mode:t}}}function de(n,t){if(!n.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:n.controls.requested_mode,option:t}}}function ue(n){if(!n.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:n.controls.safe_shutdown}}}function he(n){const t=String(n.action??"operation").replaceAll("_"," ");const e=String(n.actuator_name??"actuator");const r=String(n.result??"");if(r==="proposed")return`Would ${t} ${e}`;if(r==="executed")return`Executed ${e} ${t}`;if(r==="suppressed")return`Suppressed ${e} ${t}`;return`${r||"Operation"}: ${e} ${t}`}function mn(n){return n.replaceAll("_"," ")}function V(n,t,e){const[r,o]=t.split(".");return n?.(`component.hydronicus.entity.${r}.${o}.state.${e}`)||g(e)}function g(n){const t=mn(n);return t.charAt(0).toUpperCase()+t.slice(1)}var gn={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function kt(n,t){return n?.(`component.climate.entity_component._.state.${t}`)||gn[t]||g(t)}function St(n){if(n.thermostat.kind!=="hydronicus")return[];return[...new Set(n.thermostat.hvac_modes??[])]}function wt(n){if(n.dry_run||n.mode==="dry_run")return"Dry run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"Live";return g(n.mode)}function pe(n){if(n.dry_run||n.mode==="dry_run")return"dry-run";if(n.mode==="mixed"&&!n.forced_shadow.length)return"live";return n.mode.replaceAll("_","-")}function me(n){const{active_name:t,recommended_name:e}=n.plant.source;if(!n.sources.length&&!t&&!e)return null;const r=[t??"None active"];if(e&&e!==t)r.push(`recommended ${e}`);return r.join(" \xB7 ")}var fn={zone:"Room",circuit:"Loop"};var bn={plant_initializing:"Starting",plant_unavailable:"Plant unavailable",binding_unavailable:"Entity unavailable",zone_sensor_blocked:"Sensor blocked",zone_mode_blocked:"Room blocked",cooling_blocked:"Cooling blocked",actuator_mismatch:"Equipment mismatch",actuator_blocked:"Equipment blocked",mode_changeover:"Mode changeover"};function ge(n){const t=bn[n.code]??g(n.code);return n.scope!=="plant"&&n.name?`${n.name} \xB7 ${t}`:t}function Ct(n){return fn[n]??g(n)}function fe(n){return[...new Set(n.thermostat.preset_modes)].filter(t=>t!=="none")}function be(n,t,e=P){if(n.thermostat.target_temperature===null)return null;return ne(n.thermostat.target_temperature,t,e)}var yn="hydronicus/subscribe_plant";var vn=1e3;var _n=6e4;var xn={setTimeout:(n,t)=>globalThis.setTimeout(n,t),clearTimeout:n=>globalThis.clearTimeout(n)};var ye={plant_not_found:"not_found",unauthorized:"unauthorized"};function ve(n){return n!==void 0&&Object.hasOwn(ye,n)?ye[n]:void 0}function $n(n){return typeof n==="object"&&n!==null&&"code"in n?String(n.code):void 0}function B(n,t){if(n instanceof Error)return n.message;if(typeof n==="object"&&n!==null&&"message"in n&&n.message){return String(n.message)}return t}function At(n){if(!n)return;try{void Promise.resolve(n()).catch(()=>void 0)}catch{}}var G=class{constructor(t,e=xn){this.host=t;this.scheduler=e}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(t,e){if(t===this.connection&&e===this.plantId)return;this.disconnect();if(!t||!e)return;this.connection=t;this.plantId=e;t.addEventListener?.("disconnected",this.handleDisconnected);t.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;At(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const t=this.connection;const e=this.plantId;if(!t||!e)return;this.cancelRetry();const r=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}t.subscribeMessage(o=>this.handleEvent(r,o),{type:yn,plant_id:e},{resubscribe:false}).then(o=>{if(r!==this.generation){At(o);return}this.unsubscribe=o}).catch(o=>{if(r!==this.generation)return;this.handleError(o)})}handleEvent(t,e){if(t!==this.generation)return;if(e.snapshot!==void 0&&e.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(e.snapshot);return}if(e.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const r=ve(e.status);if(r)this.stop({kind:r})}handleError(t){const e=ve($n(t));if(e){this.stop({kind:e});return}const r=Math.min(vn*2**this.attempt,_n);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:r,message:B(t,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},r)}stop(t){this.cancelRetry();this.generation+=1;At(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(t)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(t){this.current=t;this.host.onStatus(t)}};var M={status:{kind:"idle"},snapshot:null,snapshotError:null};var kn=new Set(["idle","unavailable","not_found","unauthorized"]);var Et=class{listeners=new Set;current=M;stream;constructor(t){this.stream=new G({onStatus:e=>this.statusChanged(e),onSnapshot:e=>this.snapshotReceived(e)},t)}get state(){return this.current}open(t,e){this.stream.connect(t,e)}close(){this.stream.disconnect()}statusChanged(t){const e=kn.has(t.kind)?null:this.current.snapshot;this.publish({...this.current,status:t,snapshot:e})}snapshotReceived(t){try{this.publish({...this.current,snapshot:oe(t),snapshotError:null})}catch(e){this.publish({...this.current,snapshot:null,snapshotError:B(e,"Unsupported Hydronicus snapshot.")})}}publish(t){this.current=t;for(const e of[...this.listeners])e(t)}};var Pt=class{constructor(t){this.scheduler=t}scheduler;feeds=new WeakMap;subscribe(t,e,r){let o=this.feeds.get(t);if(!o){o=new Map;this.feeds.set(t,o)}let s=o.get(e);const i=!s;if(!s){s=new Et(this.scheduler);o.set(e,s)}s.listeners.add(r);if(i)s.open(t,e);else r(s.state);const u=o;const l=s;let d=false;return()=>{if(d)return;d=true;l.listeners.delete(r);if(l.listeners.size)return;queueMicrotask(()=>{if(l.listeners.size||u.get(e)!==l)return;u.delete(e);l.close()})}}snapshot(t,e,r=2e3){return new Promise(o=>{let s=false;const i=d=>{if(s)return;s=true;clearTimeout(u);queueMicrotask(()=>l());o(d)};const u=setTimeout(()=>i(null),r);const l=this.subscribe(t,e,d=>{if(d.snapshot)i(d.snapshot);else if(["not_found","unauthorized"].includes(d.status.kind)||d.snapshotError)i(null)})})}};var _e=new Pt;var xe=it`
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
`;var Sn=L("hassConnection");var wn=L("hassApi");var Cn=L("hassConfig");var An=L("hassInternationalization");var J=class extends ${static properties={preview:{type:Boolean},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_plant:{state:true},_actionError:{state:true}};static styles=xe;_hass;_callService;_fromContext=new Set;_release;_followed;constructor(){super();this.preview=false;this._connection=void 0;this._unit=P;this._locale=void 0;this._localize=void 0;this._plant=M;this._actionError=null;new _(this,{context:Sn,subscribe:true,callback:t=>{this._fromContext.add("connection");this._connection=t?.connection}});new _(this,{context:wn,subscribe:true,callback:t=>{this._fromContext.add("api");this._callService=t?.callService}});new _(this,{context:Cn,subscribe:true,callback:t=>{this._fromContext.add("config");this._unit=vt(t?.config?.unit_system)}});new _(this,{context:An,subscribe:true,callback:t=>{this._fromContext.add("i18n");this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}})}set hass(t){this._hass=t;if(!this._fromContext.has("connection"))this._connection=t?.connection;if(!this._fromContext.has("api"))this._callService=t?(...e)=>t.callService(...e):void 0;if(!this._fromContext.has("config"))this._unit=vt(t?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}}get hass(){return this._hass}resetPlant(){this._plant=M;this._actionError=null}connectedCallback(){super.connectedCallback();this._follow()}disconnectedCallback(){this._unfollow();super.disconnectedCallback()}updated(t){super.updated(t);this._syncSelectValues();if(!this.isConnected)return;this._follow();if(this._connection&&(t.has("_connection")||this.preview))void U.load(this._connection)}_follow(){const t=this._connection;const e=this.plantId||void 0;const r=this._followed;if(r&&r.connection===t&&r.plantId===e)return;this._unfollow();if(!t||!e)return;this._followed={connection:t,plantId:e};this._release=_e.subscribe(t,e,o=>{this._plant=o;this.plantStateChanged?.(o)})}_unfollow(){this._release?.();this._release=void 0;this._followed=void 0;this._plant=M;this.plantStateChanged?.(M)}_syncSelectValues(){for(const t of this.renderRoot.querySelectorAll("select[data-value]")){const e=t.dataset.value??"";if(t.value!==e)t.value=e}}get renderContext(){return{unit:this._unit,locale:this._locale,localize:this._localize,moreInfo:t=>this.moreInfo(t),call:t=>this.call(t)}}moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:t}}))}call(t){const e=this._callService;if(!t||!e)return;e(t.domain,t.service,t.data,void 0,false).then(()=>{this._actionError=null},r=>{this._actionError=B(r,"The Home Assistant action failed.");this.requestUpdate()})}dismissActionError=()=>{this._actionError=null}};function $e(n,t,e,r){const o=n.unit;if(t===null){return a`<div class=${r}><span class="metric-value">--</span><span class="metric-label">${e}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${r}><span class="metric-value">${xt(t,o,n.locale)}</span><span class="metric-unit">${o}</span><span class="metric-label">${e}</span></div>`}function ke(n,t,e){const r=be(t,e,n.unit);if(r!==null)n.call(ae(t,r))}function En(n,t,e){if(e===t.thermostat.hvac_mode)return;n.call(ce(t,e))}function Pn(n,t,e){n.call(le(t,e.target.value))}function Se(n,t,e){const r=t.thermostat;const o=r.kind==="hydronicus";const s=t.cooling.demand?"cooling":t.demand?"heating":"none";const i=s!=="none";const u=r.hvac_mode==="off";const{unit:l,locale:d,localize:p}=n;const h=b(_t(l),d,l===P?1:0);const m=r.control_entity_id;const f=Boolean(m)&&r.target_temperature!==null;const k=fe(t);const Ht=St(t);const tt=r.hvac_mode?kt(p,r.hvac_mode):null;const De=u&&!t.blocked?tt??"Off":g(t.phase);const zt=i?`${s==="cooling"?"Cooling":"Heating"} demand active`:u?"Thermostat off":"No demand";const et=`zone-${t.id}`;const Lt=m?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>n.moreInfo(m)}>${t.name}</button>`:t.name;const Ie=e.headingLevel===2?a`<h2 class="zone-title" id=${et}>${Lt}</h2>`:a`<h4 class="zone-title" id=${et}>${Lt}</h4>`;return a`<article class="zone" data-phase=${t.phase} data-hvac-mode=${r.hvac_mode??"unknown"} data-demand=${String(i)} data-demand-kind=${s} data-blocked=${String(t.blocked)} aria-labelledby=${et}>
    <div class="row"><div>${Ie}<p class="meta zone-owner">${o?"Hydronicus thermostat":`External thermostat \xB7 read-only${tt?` \xB7 ${tt}`:""}`}</p></div><span class=${`phase${t.blocked?" state blocked":""}${u?" off":""}`}>${De}</span></div>
    <div class="temperature-panel">
      ${$e(n,r.current_temperature,"Current","metric")}
      ${$e(n,r.target_temperature,"Target","metric target")}
    </div>
    <p class="meta zone-note" dir="auto">${o?zt:`${zt} \xB7 ${r.explanation}`}</p>
    <ul class="diagnostic-list" aria-label="Room diagnostics">
      <li class="diagnostic-chip" dir="auto">${b(t.sensor_status.usable,d,0)} sensor${t.sensor_status.usable===1?"":"s"} ready</li>
      ${t.sensor_status.optional_excluded?a`<li class="diagnostic-chip warning" dir="auto">${b(t.sensor_status.optional_excluded,d,0)} optional excluded</li>`:c}
      ${t.sensor_status.required_blocking?a`<li class="diagnostic-chip danger" dir="auto">${b(t.sensor_status.required_blocking,d,0)} required blocked</li>`:c}
      ${t.cooling.dew_point===null?c:a`<li class="diagnostic-chip" dir="auto">Dew point ${xt(t.cooling.dew_point,l,d)} ${l}</li>`}
      ${t.cooling.condensation_margin===null?c:a`<li class="diagnostic-chip ${t.cooling.blocked?"danger":""}" dir="auto">Margin ${re(t.cooling.condensation_margin,l,d)} ${l}</li>`}
    </ul>
    ${r.preset&&r.preset!=="none"?a`<p class="meta zone-note" dir="auto">Preset: ${g(r.preset)}</p>`:c}
    ${t.blocked_reason?a`<p class="meta zone-note" dir="auto">${t.blocked_reason}</p>`:c}
    ${t.coupling_group_ids.length?a`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>`:c}
    ${o?a`${Ht.length?a`<div class="hvac-modes" role="group" aria-label=${`${t.name} HVAC mode`}>${Ht.map(y=>a`<button type="button" class="hvac-mode" data-mode=${y} aria-pressed=${String(y===r.hvac_mode)} ?disabled=${!m} @click=${()=>En(n,t,y)}>${kt(p,y)}</button>`)}</div>`:c}
          <div class="zone-actions">
            <button type="button" dir="ltr" ?disabled=${!f} aria-label=${`Decrease ${t.name} target by ${h} ${l}`} @click=${()=>ke(n,t,-1)}>−${h}</button>
            <button type="button" dir="ltr" ?disabled=${!f} aria-label=${`Increase ${t.name} target by ${h} ${l}`} @click=${()=>ke(n,t,1)}>+${h}</button>
            ${k.length?a`<select class="preset" data-value=${r.preset??"none"} aria-label=${`${t.name} preset`} ?disabled=${!m} @change=${y=>Pn(n,t,y)}>${["none",...k].map(y=>a`<option value=${y}>${g(y)}</option>`)}</select>`:c}
          </div>`:a`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
  </article>`}var Rt=["auto","idle","heating","cooling"];function Rn(n,t){const e=t.plant;const r=`Mode ${V(n.localize,"select.requested_mode",e.requested_mode)}`;if(e.requested_mode==="auto"||e.requested_mode===e.active_mode)return r;return`${r} \xB7 now ${V(n.localize,"sensor.operating_mode",e.active_mode)}`}function we(n,t,e){const r=t.plant;const o=r.execution_boundary;const s=t.controls.requested_mode;const i=Rt.includes(r.requested_mode)?Rt:[...Rt,r.requested_mode];const u=me(t);const l=d=>n.call(de(t,d.target.value));return a`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${s?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>n.moreInfo(s)}>${r.name}</button>`:r.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${V(n.localize,"sensor.controller_status",r.status)}</span>
            <span class="meta mode-detail">${Rn(n,t)}</span>
          </div>
          ${u===null?c:a`<p class="meta source-line" dir="auto"><strong>Source</strong> ${u}</p>`}
          <p class="meta" dir="auto">${r.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${pe(o)}"><span class="visually-hidden">Execution boundary: </span>${wt(o)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${r.requested_mode} ?disabled=${!s} @change=${l}>
          ${i.map(d=>a`<option value=${d}>${V(n.localize,"select.requested_mode",d)}</option>`)}
        </select></label>
        ${e}
      </div>
    </header>`}function Ce(n){return a`<div class="boundary" role="status">
      <span class="boundary-orb" aria-hidden="true"></span>
      <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${n.plant.execution_boundary.message||`${wt(n.plant.execution_boundary)} execution boundary is active.`}</strong></p>
    </div>`}function Ae(n,t){const e=se(t);if(!e.length)return c;return a`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${b(e.length,n.locale,0)}</span></div>${e.slice(0,3).map(r=>{const o=r.severity==="error"||r.severity==="critical";return a`<p class="alert ${o?"error":""}" data-severity=${r.severity} dir="auto"><strong>${ge(r)}</strong><span> · ${r.message}</span></p>`})}</section>`}function Ee(n,t){return a`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${b(t.zones.length,n.locale,0)} visible</span></div><div class="zone-grid">${t.zones.length?t.zones.map(e=>Se(n,e,{headingLevel:4})):a`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`}function Pe(n){if(!n.delivery_paths.length)return c;return a`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${n.delivery_paths.map(t=>a`<article class="path" data-status=${t.status} data-flowing=${String($t(t.status))}>
    <div class="path-head"><div class="path-heading"><strong>${n.zones.find(e=>e.id===t.zone_id)?.name??t.zone_id}</strong></div><div class="status-line"><span class="state ${t.status}">${g(t.status)}</span>${t.coupled?a`<span class="meta">shares equipment</span>`:c}</div></div>
    <ol class="path-track" aria-label="Ordered hydraulic delivery path">${t.nodes.map((e,r)=>a`<li class="path-step">${r?a`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" data-kind=${e.kind} data-state=${e.state} data-flowing=${String($t(e.state))}><span class="node-kind">${Ct(e.kind)}</span><span class="node-name">${e.name}</span><span class="node-state">${g(e.state)}</span></span></li>`)}</ol>
    ${t.problem?a`<p class="meta path-problem" dir="auto">${t.problem}</p>`:c}
  </article>`)}</div></section>`}function Re(n){if(!n.actuators.length)return c;return a`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${n.actuators.map(t=>a`<article class="actuator" data-state=${t.state}><div class="row"><strong>${t.name}</strong><span class="state actuator-state ${t.state}">${g(t.state)}</span></div><p class="meta" dir="auto">${g(t.kind)} · ${t.reason??"No additional explanation."}</p>${t.active_consumers.length?a`<ul class="consumer-list" aria-label="Loops using this equipment">${t.active_consumers.map(e=>a`<li class="consumer-chip" title=${e.id}><strong>${e.name}</strong></li>`)}</ul>`:a`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}function Te(n){return a`<section><details><summary>Controller explanations</summary>${n.explanations.map(t=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${t.name??Ct(t.scope)}</strong> · ${t.message}</p></div>`)}</details></section>`}function He(n,t){const e=Object.values(t.execution.operations).flat();if(!e.length)return c;return a`<section><details open><summary>Latest operation outcomes (${b(e.length,n.locale,0)})</summary>${e.map(r=>{const o=String(r.result??"unknown");return a`<div class="operation" data-result=${o}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${he(r)}</strong><br><span class="meta">${String(r.reason??r.explanation??"")}</span></p></div>`})}</details></section>`}function ze(n){return`Retrying in ${Math.round(n/1e3)} s.`}function R(n,t,e,r,o){return a`<ha-card class="state-card" data-visual=${r==="alert"?"attention":"idle"}>
    <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">${n}</p><h2>${t}</h2></div></div>
    <p class=${r==="alert"?"notice error":"notice"} role=${r} dir="auto">${e}</p>
    ${o?a`<p class="meta" dir="auto">${o}</p>`:c}
  </ha-card>`}function Tn(n){return a`<ha-card class="loading-card" role="status" aria-busy="true">
    <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
    <div class="loading-panel"></div>
    <p class="muted">${n?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
  </ha-card>`}function Le(n){return n.snapshotError?null:n.snapshot}function Me(n,t){if(t.snapshotError){return R(n,"Card update needed",t.snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const e=t.status;switch(e.kind){case"not_found":return R(n,"Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return R(n,"No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return R(n,"Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return R(n,"Connection needs attention",e.message,"alert",ze(e.delayMs));default:return Tn(e.kind==="reconnecting")}}function Ue(n){if(n.kind==="reconnecting"){return a`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(n.kind==="retrying"){return a`<p class="notice" role="status" dir="auto">${n.message} ${ze(n.delayMs)} The values below may be out of date.</p>`}return c}function qe(n,t){if(!n)return c;return a`<div class="action-error" role="alert"><span dir="auto">${n}</span><button type="button" @click=${t}>Dismiss</button></div>`}var Hn=1200;var Tt="Hydronicus Plant";var Q=class extends J{static properties={_config:{state:true},_holdingShutdown:{state:true}};_holdTimer=null;constructor(){super();this._config=void 0;this._holdingShutdown=false}static async getConfigForm(){return Ut()}static async getStubConfig(t){return Mt(t)}setConfig(t){const e=ot(t);if(e.plant!==this._config?.plant)this.resetPlant();this._config=e}get plantId(){return this._config?.plant}getCardSize(){const t=this._plant.snapshot;if(!t)return 4;let e=4;const r=Math.min(t.alerts.length,3);if(r)e+=1+r;e+=1+Math.max(1,t.zones.length)*5;if(t.delivery_paths.length)e+=1+t.delivery_paths.length*3;if(t.actuators.length)e+=1+t.actuators.length*2;e+=1;const o=Object.values(t.execution.operations).flat().length;if(o)e+=1+o;return e}getGridOptions(){return{columns:12,min_columns:6}}disconnectedCallback(){this._clearHold();super.disconnectedCallback()}plantStateChanged(t){if(!t.snapshot)this._clearHold()}render(){const t=this._config;if(!t||!t.plant){return R(Tt,Tt,"Select a Hydronicus Plant in the card editor.","status")}const e=this._plant;const r=Le(e);if(!r)return Me(Tt,e);const o=this.renderContext;return a`<ha-card class=${t.density??"comfortable"} data-visual=${ie(r)}>
      ${we(o,r,this._renderShutdown(r))}
      ${Ue(e.status)}
      ${qe(this._actionError,this.dismissActionError)}
      ${Ce(r)}
      ${Ae(o,r)}
      ${Ee(o,r)}
      ${Pe(r)}
      ${Re(r)}
      ${Te(r)}
      ${He(o,r)}
    </ha-card>`}_renderShutdown(t){const e=!t.controls.safe_shutdown;const r=t.plant.execution_boundary.dry_run;return a`<button type="button" class=${`shutdown${r?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${e} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_startHold(){if(!this._plant.snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;const t=this._plant.snapshot;if(t)this.call(ue(t))},Hn)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=t=>{if(t.button!==void 0&&t.button>0)return;this._startHold()};_keyHoldStart=t=>{if(t.key!=="Enter"&&t.key!==" ")return;t.preventDefault();if(!t.repeat)this._startHold()};_keyHoldEnd=t=>{if(t.key==="Enter"||t.key===" ")this._clearHold()};_preventContextMenu=t=>{t.preventDefault()}};function Ne(n){if(!n.get(T))n.define(T,Q)}var Oe=window.customElements;Ne(Oe);void Oe.whenDefined("home-assistant").then(()=>{Ne(window.customElements)});window.customCards=window.customCards??[];if(!window.customCards.some(n=>n.type===T)){window.customCards.push({type:T,name:"Hydronicus Plant",version:"0.1.0-rc.6",description:"Topology-driven Hydronicus Plant status and controls.",preview:true,documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
