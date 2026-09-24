var A="hydronicus-plant-card";var Y=`custom:${A}`;var Kt="hydronicus/list_plants";var Jt=["comfortable","compact"];function K(r){if(!r||typeof r!=="object"){throw new Error("Hydronicus Plant card requires a configuration.")}const t=r;if(t.type!==Y){throw new Error(`Hydronicus Plant card type must be ${Y}.`)}if(typeof t.plant!=="string"){throw new Error("Hydronicus Plant card requires one Plant UUID in `plant`.")}const e=t.density??"comfortable";if(!Jt.includes(e)){throw new Error("Hydronicus Plant card density must be comfortable or compact.")}return{type:Y,plant:t.plant.trim(),density:e}}var G=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(t){if(this.connection===t&&this.pending)return this.pending;this.connection=t;this.pending=t.sendMessagePromise({type:Kt}).then(e=>{this.plants=Array.isArray(e.plants)?e.plants:[];return this.plants}).catch(()=>{if(this.connection===t)this.pending=null;return this.plants});return this.pending}async settled(t=2e3){if(!this.pending)return this.plants;let e;const n=new Promise(s=>{e=setTimeout(()=>s(this.plants),t)});try{return await Promise.race([this.pending,n])}finally{clearTimeout(e)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var z=new G;async function yt(r){const t=r?.connection?await z.load(r.connection):z.known;return{plant:t[0]?.id??"",density:"comfortable"}}var Qt={plant:"Hydronicus Plant",density:"Density"};var te={plant:"The Plant this card shows. Only Plants you can read are listed.",density:"Compact uses less spacing for dense dashboards."};async function vt(){const r=await z.settled();return{schema:[{name:"plant",required:true,selector:{select:{mode:"dropdown",custom_value:true,options:r.map(t=>({value:t.id,label:t.name}))}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}}],computeLabel:t=>Qt[t.name],computeHelper:t=>te[t.name],assertConfig:t=>{K(t)}}}var $=class extends Event{constructor(t,e,n,s){super("context-request",{bubbles:true,composed:true}),this.context=t,this.contextTarget=e,this.callback=n,this.subscribe=s??false}};function E(r){return r}var b=class{constructor(t,e,n,s){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(i,o)=>{this.unsubscribe&&(this.unsubscribe!==o&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=i,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(i,o)),this.unsubscribe=o},this.host=t,void 0!==e.context){const i=e;this.context=i.context,this.callback=i.callback,this.subscribe=i.subscribe??false}else this.context=e,this.callback=n,this.subscribe=s??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new $(this.context,this.host,this.t,this.subscribe))}};var F=globalThis;var I=F.ShadowRoot&&(void 0===F.ShadyCSS||F.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var J=Symbol();var _t=new WeakMap;var R=class{constructor(t,e,n){if(this._$cssResult$=true,n!==J)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(I&&void 0===t){const n=void 0!==e&&1===e.length;n&&(t=_t.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),n&&_t.set(e,t))}return t}toString(){return this.cssText}};var xt=r=>new R("string"==typeof r?r:r+"",void 0,J);var Q=(r,...t)=>{const e=1===r.length?r[0]:t.reduce((n,s,i)=>n+(o=>{if(true===o._$cssResult$)return o.cssText;if("number"==typeof o)return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+r[i+1],r[0]);return new R(e,r,J)};var $t=(r,t)=>{if(I)r.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const e of t){const n=document.createElement("style"),s=F.litNonce;void 0!==s&&n.setAttribute("nonce",s),n.textContent=e.cssText,r.appendChild(n)}};var tt=I?r=>r:r=>r instanceof CSSStyleSheet?(t=>{let e="";for(const n of t.cssRules)e+=n.cssText;return xt(e)})(r):r;var{is:ne,defineProperty:re,getOwnPropertyDescriptor:se,getOwnPropertyNames:ie,getOwnPropertySymbols:oe,getPrototypeOf:ae}=Object;var j=globalThis;var kt=j.trustedTypes;var le=kt?kt.emptyScript:"";var ce=j.reactiveElementPolyfillSupport;var U=(r,t)=>r;var et={toAttribute(r,t){switch(t){case Boolean:r=r?le:null;break;case Object:case Array:r=null==r?r:JSON.stringify(r)}return r},fromAttribute(r,t){let e=r;switch(t){case Boolean:e=null!==r;break;case Number:e=null===r?null:Number(r);break;case Object:case Array:try{e=JSON.parse(r)}catch(n){e=null}}return e}};var St=(r,t)=>!ne(r,t);var wt={attribute:true,type:String,converter:et,reflect:false,useDefault:false,hasChanged:St};Symbol.metadata??=Symbol("metadata"),j.litPropertyMetadata??=new WeakMap;var y=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=wt){if(e.state&&(e.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=true),this.elementProperties.set(t,e),!e.noAccessor){const n=Symbol(),s=this.getPropertyDescriptor(t,n,e);void 0!==s&&re(this.prototype,t,s)}}static getPropertyDescriptor(t,e,n){const{get:s,set:i}=se(this.prototype,t)??{get(){return this[e]},set(o){this[e]=o}};return{get:s,set(o){const d=s?.call(this);i?.call(this,o),this.requestUpdate(t,d,n)},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??wt}static _$Ei(){if(this.hasOwnProperty(U("elementProperties")))return;const t=ae(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(U("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(U("properties"))){const e=this.properties,n=[...ie(e),...oe(e)];for(const s of n)this.createProperty(s,e[s])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[n,s]of e)this.elementProperties.set(n,s)}this._$Eh=new Map;for(const[e,n]of this.elementProperties){const s=this._$Eu(e,n);void 0!==s&&this._$Eh.set(s,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const n=new Set(t.flat(1/0).reverse());for(const s of n)e.unshift(tt(s))}else void 0!==t&&e.push(tt(t));return e}static _$Eu(t,e){const n=e.attribute;return false===n?void 0:"string"==typeof n?n:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const n of e.keys())this.hasOwnProperty(n)&&(t.set(n,this[n]),delete this[n]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return $t(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,n){this._$AK(t,n)}_$ET(t,e){const n=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,n);if(void 0!==s&&true===n.reflect){const i=(void 0!==n.converter?.toAttribute?n.converter:et).toAttribute(e,n.type);this._$Em=t,null==i?this.removeAttribute(s):this.setAttribute(s,i),this._$Em=null}}_$AK(t,e){const n=this.constructor,s=n._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const i=n.getPropertyOptions(s),o="function"==typeof i.converter?{fromAttribute:i.converter}:void 0!==i.converter?.fromAttribute?i.converter:et;this._$Em=s;const d=o.fromAttribute(e,i.type);this[s]=d??this._$Ej?.get(s)??d,this._$Em=null}}requestUpdate(t,e,n,s=false,i){if(void 0!==t){const o=this.constructor;if(false===s&&(i=this[t]),n??=o.getPropertyOptions(t),!((n.hasChanged??St)(i,e)||n.useDefault&&n.reflect&&i===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,n))))return;this.C(t,e,n)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:n,reflect:s,wrapped:i},o){n&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),true!==i||void 0!==o)||(this._$AL.has(t)||(this.hasUpdated||n||(e=void 0),this._$AL.set(t,e)),true===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(e){Promise.reject(e)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[s,i]of this._$Ep)this[s]=i;this._$Ep=void 0}const n=this.constructor.elementProperties;if(n.size>0)for(const[s,i]of n){const{wrapped:o}=i,d=this[s];true!==o||this._$AL.has(s)||void 0===d||this.C(s,void 0,i,d)}}let t=false;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(e)):this._$EM()}catch(n){throw t=false,this._$EM(),n}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return true}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};y.elementStyles=[],y.shadowRootOptions={mode:"open"},y[U("elementProperties")]=new Map,y[U("finalized")]=new Map,ce?.({ReactiveElement:y}),(j.reactiveElementVersions??=[]).push("2.1.2");var lt=globalThis;var Ct=r=>r;var V=lt.trustedTypes;var At=V?V.createPolicy("lit-html",{createHTML:r=>r}):void 0;var Rt="$lit$";var _=`lit$${Math.random().toFixed(9).slice(2)}$`;var Ut="?"+_;var de=`<${Ut}>`;var S=document;var M=()=>S.createComment("");var O=r=>null===r||"object"!=typeof r&&"function"!=typeof r;var ct=Array.isArray;var ue=r=>ct(r)||"function"==typeof r?.[Symbol.iterator];var nt="[ 	\n\f\r]";var L=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Et=/-->/g;var Pt=/>/g;var k=RegExp(`>|${nt}(?:([^\\s"'>=/]+)(${nt}*=${nt}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var Tt=/'/g;var Ht=/"/g;var Lt=/^(?:script|style|textarea|title)$/i;var dt=r=>(t,...e)=>({_$litType$:r,strings:t,values:e});var a=dt(1);var dn=dt(2);var un=dt(3);var C=Symbol.for("lit-noChange");var c=Symbol.for("lit-nothing");var zt=new WeakMap;var w=S.createTreeWalker(S,129);function Mt(r,t){if(!ct(r)||!r.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==At?At.createHTML(t):t}var he=(r,t)=>{const e=r.length-1,n=[];let s,i=2===t?"<svg>":3===t?"<math>":"",o=L;for(let d=0;d<e;d++){const l=r[d];let h,m,u=-1,f=0;for(;f<l.length&&(o.lastIndex=f,m=o.exec(l),null!==m);)f=o.lastIndex,o===L?"!--"===m[1]?o=Et:void 0!==m[1]?o=Pt:void 0!==m[2]?(Lt.test(m[2])&&(s=RegExp("</"+m[2],"g")),o=k):void 0!==m[3]&&(o=k):o===k?">"===m[0]?(o=s??L,u=-1):void 0===m[1]?u=-2:(u=o.lastIndex-m[2].length,h=m[1],o=void 0===m[3]?k:'"'===m[3]?Ht:Tt):o===Ht||o===Tt?o=k:o===Et||o===Pt?o=L:(o=k,s=void 0);const v=o===k&&r[d+1].startsWith("/>")?" ":"";i+=o===L?l+de:u>=0?(n.push(h),l.slice(0,u)+Rt+l.slice(u)+_+v):l+_+(-2===u?d:v)}return[Mt(r,i+(r[e]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),n]};var N=class r{constructor({strings:t,_$litType$:e},n){let s;this.parts=[];let i=0,o=0;const d=t.length-1,l=this.parts,[h,m]=he(t,e);if(this.el=r.createElement(h,n),w.currentNode=this.el.content,2===e||3===e){const u=this.el.content.firstChild;u.replaceWith(...u.childNodes)}for(;null!==(s=w.nextNode())&&l.length<d;){if(1===s.nodeType){if(s.hasAttributes())for(const u of s.getAttributeNames())if(u.endsWith(Rt)){const f=m[o++],v=s.getAttribute(u).split(_),D=/([.?@])?(.*)/.exec(f);l.push({type:1,index:i,name:D[2],strings:v,ctor:"."===D[1]?st:"?"===D[1]?it:"@"===D[1]?ot:T}),s.removeAttribute(u)}else u.startsWith(_)&&(l.push({type:6,index:i}),s.removeAttribute(u));if(Lt.test(s.tagName)){const u=s.textContent.split(_),f=u.length-1;if(f>0){s.textContent=V?V.emptyScript:"";for(let v=0;v<f;v++)s.append(u[v],M()),w.nextNode(),l.push({type:2,index:++i});s.append(u[f],M())}}}else if(8===s.nodeType)if(s.data===Ut)l.push({type:2,index:i});else{let u=-1;for(;-1!==(u=s.data.indexOf(_,u+1));)l.push({type:7,index:i}),u+=_.length-1}i++}}static createElement(t,e){const n=S.createElement("template");return n.innerHTML=t,n}};function P(r,t,e=r,n){if(t===C)return t;let s=void 0!==n?e._$Co?.[n]:e._$Cl;const i=O(t)?void 0:t._$litDirective$;return s?.constructor!==i&&(s?._$AO?.(false),void 0===i?s=void 0:(s=new i(r),s._$AT(r,e,n)),void 0!==n?(e._$Co??=[])[n]=s:e._$Cl=s),void 0!==s&&(t=P(r,s._$AS(r,t.values),s,n)),t}var rt=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:n}=this._$AD,s=(t?.creationScope??S).importNode(e,true);w.currentNode=s;let i=w.nextNode(),o=0,d=0,l=n[0];for(;void 0!==l;){if(o===l.index){let h;2===l.type?h=new q(i,i.nextSibling,this,t):1===l.type?h=new l.ctor(i,l.name,l.strings,this,t):6===l.type&&(h=new at(i,this,t)),this._$AV.push(h),l=n[++d]}o!==l?.index&&(i=w.nextNode(),o++)}return w.currentNode=S,s}p(t){let e=0;for(const n of this._$AV)void 0!==n&&(void 0!==n.strings?(n._$AI(t,n,e),e+=n.strings.length-2):n._$AI(t[e])),e++}};var q=class r{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,n,s){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=n,this.options=s,this._$Cv=s?.isConnected??true}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=P(this,t,e),O(t)?t===c||null==t||""===t?(this._$AH!==c&&this._$AR(),this._$AH=c):t!==this._$AH&&t!==C&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):ue(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==c&&O(this._$AH)?this._$AA.nextSibling.data=t:this.T(S.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:n}=t,s="number"==typeof n?this._$AC(t):(void 0===n.el&&(n.el=N.createElement(Mt(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===s)this._$AH.p(e);else{const i=new rt(s,this),o=i.u(this.options);i.p(e),this.T(o),this._$AH=i}}_$AC(t){let e=zt.get(t.strings);return void 0===e&&zt.set(t.strings,e=new N(t)),e}k(t){ct(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let n,s=0;for(const i of t)s===e.length?e.push(n=new r(this.O(M()),this.O(M()),this,this.options)):n=e[s],n._$AI(i),s++;s<e.length&&(this._$AR(n&&n._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(false,true,e);t!==this._$AB;){const n=Ct(t).nextSibling;Ct(t).remove(),t=n}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}};var T=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,n,s,i){this.type=1,this._$AH=c,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=i,n.length>2||""!==n[0]||""!==n[1]?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=c}_$AI(t,e=this,n,s){const i=this.strings;let o=false;if(void 0===i)t=P(this,t,e,0),o=!O(t)||t!==this._$AH&&t!==C,o&&(this._$AH=t);else{const d=t;let l,h;for(t=i[0],l=0;l<i.length-1;l++)h=P(this,d[n+l],e,l),h===C&&(h=this._$AH[l]),o||=!O(h)||h!==this._$AH[l],h===c?t=c:t!==c&&(t+=(h??"")+i[l+1]),this._$AH[l]=h}o&&!s&&this.j(t)}j(t){t===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}};var st=class extends T{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===c?void 0:t}};var it=class extends T{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==c)}};var ot=class extends T{constructor(t,e,n,s,i){super(t,e,n,s,i),this.type=5}_$AI(t,e=this){if((t=P(this,t,e,0)??c)===C)return;const n=this._$AH,s=t===c&&n!==c||t.capture!==n.capture||t.once!==n.once||t.passive!==n.passive,i=t!==c&&(n===c||s);s&&this.element.removeEventListener(this.name,this,n),i&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}};var at=class{constructor(t,e,n){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(t){P(this,t)}};var pe=lt.litHtmlPolyfillSupport;pe?.(N,q),(lt.litHtmlVersions??=[]).push("3.3.3");var Ot=(r,t,e)=>{const n=e?.renderBefore??t;let s=n._$litPart$;if(void 0===s){const i=e?.renderBefore??null;n._$litPart$=s=new q(t.insertBefore(M(),i),i,void 0,e??{})}return s._$AI(r),s};var ut=globalThis;var x=class extends y{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Ot(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return C}};x._$litElement$=true,x["finalized"]=true,ut.litElementHydrateSupport?.({LitElement:x});var me=ut.litElementPolyfillSupport;me?.({LitElement:x});(ut.litElementVersions??=[]).push("4.2.2");var H="\xB0C";var ge=5;var fe=35;function ht(r){return r?.temperature==="\xB0F"?"\xB0F":H}function Z(r,t){return t==="\xB0F"?r*9/5+32:r}function be(r,t){return t==="\xB0F"?r*9/5:r}function pt(r){return r==="\xB0F"?1:.5}function qt(r,t,e){const n=pt(e);const s=Z(r,e);const i=s/n;const o=(t>0?Math.floor(i+1e-9)+1:Math.ceil(i-1e-9)-1)*n;const d=Z(ge,e);const l=Z(fe,e);return Number(Math.min(l,Math.max(d,o)).toFixed(1))}function ye(r){switch(r?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return r?.language}}var Nt=new Map;function g(r,t,e=1){const n=ye(t);const s=t?.number_format!=="none";const i=`${JSON.stringify(n)}|${e}|${s}`;let o=Nt.get(i);if(!o){try{o=new Intl.NumberFormat(n,{minimumFractionDigits:e,maximumFractionDigits:e,useGrouping:s})}catch{o=new Intl.NumberFormat(void 0,{minimumFractionDigits:e,maximumFractionDigits:e})}Nt.set(i,o)}return o.format(r)}function mt(r,t,e){return g(Z(r,t),e)}function Dt(r,t,e){return g(be(r,t),e)}var ve=2;var _e=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function Ft(r){if(!r||typeof r!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const t=r;if(t.schema_version!==ve){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(t.schema_version)}.`)}if(!t.plant||!Array.isArray(t.zones)||!Array.isArray(t.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return t}function It(r){return[...r.alerts].sort((t,e)=>t.priority-e.priority||t.code.localeCompare(e.code)||t.scope.localeCompare(e.scope))}function jt(r){const t=r.plant.health.toLowerCase();const e=r.alerts.some(s=>s.severity==="critical"||s.severity==="error");if(r.safe_shutdown.active||e||["blocked","critical","error","failed","unhealthy"].includes(t)){return"attention"}const n=`${r.plant.active_mode} ${r.plant.status}`.toLowerCase();if(n.includes("cool"))return"cooling";if(n.includes("heat"))return"heating";return"idle"}function gt(r){return _e.has(r.toLowerCase())}function Vt(r,t){if(r.thermostat.kind!=="hydronicus"||!r.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:r.thermostat.control_entity_id,temperature:t}}}function Zt(r,t){if(r.thermostat.kind!=="hydronicus"||!r.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:r.thermostat.control_entity_id,preset_mode:t}}}function Bt(r,t){if(!r.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:r.controls.requested_mode,option:t}}}function Wt(r){if(!r.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:r.controls.safe_shutdown}}}function Xt(r){const t=String(r.action??"operation").replaceAll("_"," ");const e=String(r.actuator_name??"actuator");const n=String(r.result??"");if(n==="proposed")return`Would ${t} ${e}`;if(n==="executed")return`Executed ${e} ${t}`;if(n==="suppressed")return`Suppressed ${e} ${t}`;return`${n||"Operation"}: ${e} ${t}`}function p(r){return r.replaceAll("_"," ")}function Yt(r,t,e=H){if(r.thermostat.target_temperature===null)return null;return qt(r.thermostat.target_temperature,t,e)}var xe="hydronicus/subscribe_plant";var $e=1e3;var ke=6e4;var we={setTimeout:(r,t)=>globalThis.setTimeout(r,t),clearTimeout:r=>globalThis.clearTimeout(r)};function Se(r){return typeof r==="object"&&r!==null&&"code"in r?String(r.code):void 0}function W(r,t){if(r instanceof Error)return r.message;if(typeof r==="object"&&r!==null&&"message"in r&&r.message){return String(r.message)}return t}function ft(r){if(!r)return;try{void Promise.resolve(r()).catch(()=>void 0)}catch{}}var B=class{constructor(t,e=we){this.host=t;this.scheduler=e}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(t,e){if(t===this.connection&&e===this.plantId)return;this.disconnect();if(!t||!e)return;this.connection=t;this.plantId=e;t.addEventListener?.("disconnected",this.handleDisconnected);t.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;ft(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const t=this.connection;const e=this.plantId;if(!t||!e)return;this.cancelRetry();const n=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}t.subscribeMessage(s=>this.handleEvent(n,s),{type:xe,plant_id:e},{resubscribe:false}).then(s=>{if(n!==this.generation){ft(s);return}this.unsubscribe=s}).catch(s=>{if(n!==this.generation)return;this.handleError(s)})}handleEvent(t,e){if(t!==this.generation)return;if(e.snapshot!==void 0&&e.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(e.snapshot);return}if(e.status==="unavailable")this.setStatus({kind:"unavailable"});else if(e.status==="unauthorized")this.stop({kind:"unauthorized"});else if(e.status==="plant_not_found")this.stop({kind:"not_found"})}handleError(t){const e=Se(t);if(e==="plant_not_found"){this.stop({kind:"not_found"});return}if(e==="unauthorized"){this.stop({kind:"unauthorized"});return}const n=Math.min($e*2**this.attempt,ke);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:n,message:W(t,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},n)}stop(t){this.cancelRetry();this.generation+=1;ft(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(t)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(t){this.current=t;this.host.onStatus(t)}};var Gt=Q`
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
  .badge.mixed, .state.blocked, .state.mismatch { color: var(--hydronicus-danger); }
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
  .zone-actions { display: flex; gap: 0.35rem; margin-block-start: 0.62rem; }
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
`;var bt=["auto","idle","heating","cooling"];var Ce=1200;var Ae=E("hassConnection");var Ee=E("hassApi");var Pe=E("hassConfig");var Te=E("hassInternationalization");function He(r){return r.replaceAll("_","-")}var X=class extends x{static properties={preview:{type:Boolean},_config:{state:true},_connection:{state:true},_unit:{state:true},_locale:{state:true},_snapshot:{state:true},_snapshotError:{state:true},_stream:{state:true},_actionError:{state:true},_holdingShutdown:{state:true}};static styles=Gt;_hass;_callService;_fromContext=new Set;_plantStream;_holdTimer=null;constructor(){super();this.preview=false;this._config=void 0;this._connection=void 0;this._unit=H;this._locale=void 0;this._snapshot=null;this._snapshotError=null;this._stream={kind:"idle"};this._actionError=null;this._holdingShutdown=false;this._plantStream=new B({onStatus:t=>this._streamStatusChanged(t),onSnapshot:t=>this._snapshotReceived(t)});new b(this,{context:Ae,subscribe:true,callback:t=>{this._fromContext.add("connection");this._connection=t?.connection}});new b(this,{context:Ee,subscribe:true,callback:t=>{this._fromContext.add("api");this._callService=t?.callService}});new b(this,{context:Pe,subscribe:true,callback:t=>{this._fromContext.add("config");this._unit=ht(t?.config?.unit_system)}});new b(this,{context:Te,subscribe:true,callback:t=>{this._fromContext.add("i18n");this._locale=t?.locale??(t?.language?{language:t.language}:void 0)}})}set hass(t){this._hass=t;if(!this._fromContext.has("connection"))this._connection=t?.connection;if(!this._fromContext.has("api"))this._callService=t?(e,n,s)=>t.callService(e,n,s):void 0;if(!this._fromContext.has("config"))this._unit=ht(t?.config?.unit_system);if(!this._fromContext.has("i18n"))this._locale=t?.locale??(t?.language?{language:t.language}:void 0)}get hass(){return this._hass}static async getConfigForm(){return vt()}static async getStubConfig(t){return yt(t)}setConfig(t){const e=K(t);if(e.plant!==this._config?.plant){this._snapshot=null;this._snapshotError=null;this._actionError=null}this._config=e}getCardSize(){const t=this._snapshot;if(!t)return 4;let e=4;const n=Math.min(t.alerts.length,3);if(n)e+=1+n;e+=1+Math.max(1,t.zones.length)*5;if(t.delivery_paths.length)e+=1+t.delivery_paths.length*3;if(t.actuators.length)e+=1+t.actuators.length*2;e+=1;const s=Object.values(t.execution.operations).flat().length;if(s)e+=1+s;return e}getGridOptions(){return{columns:12,min_columns:6}}connectedCallback(){super.connectedCallback();this.requestUpdate()}disconnectedCallback(){this._plantStream.disconnect();this._clearHold();super.disconnectedCallback()}updated(t){super.updated(t);this._syncSelectValues();if(!this.isConnected)return;const e=this._config?.plant||void 0;this._plantStream.connect(this._connection,e);if(this._connection&&(t.has("_connection")||this.preview))void z.load(this._connection)}_syncSelectValues(){for(const t of this.renderRoot.querySelectorAll("select[data-value]")){const e=t.dataset.value??"";if(t.value!==e)t.value=e}}_streamStatusChanged(t){this._stream=t;if(["idle","unavailable","not_found","unauthorized"].includes(t.kind)){this._snapshot=null;this._clearHold()}}_snapshotReceived(t){try{this._snapshot=Ft(t);this._snapshotError=null}catch(e){this._snapshot=null;this._snapshotError=W(e,"Unsupported Hydronicus snapshot.")}}render(){const t=this._config;if(!t||!t.plant){return this._renderState("Hydronicus Plant","Select a Hydronicus Plant in the card editor.","status")}if(this._snapshotError){return this._renderState("Card update needed",this._snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const e=this._snapshot;const n=this._stream;if(!e){switch(n.kind){case"not_found":return this._renderState("Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return this._renderState("No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return this._renderState("Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return this._renderState("Connection needs attention",n.message,"alert",`Retrying in ${Math.round(n.delayMs/1e3)} s.`);default:return this._renderLoading(n.kind==="reconnecting")}}return a`<ha-card class=${t.density??"comfortable"} data-visual=${jt(e)}>
      ${this._renderHeader(e)}
      ${this._renderStreamNotice(n)}
      ${this._actionError?a`<div class="action-error" role="alert"><span>${this._actionError}</span><button type="button" @click=${this._dismissActionError}>Dismiss</button></div>`:c}
      <div class="boundary" role="status">
        <span class="boundary-orb" aria-hidden="true"></span>
        <p class="boundary-copy"><span class="control-label">Execution boundary</span><strong>${e.plant.execution_boundary.message||`${p(e.plant.execution_boundary.mode)} execution boundary is active.`}</strong></p>
      </div>
      ${this._renderAlerts(e)}
      ${this._renderZones(e)}
      ${this._renderPaths(e)}
      ${this._renderActuators(e)}
      ${this._renderExplanations(e)}
      ${this._renderOperations(e)}
    </ha-card>`}_renderState(t,e,n,s){return a`<ha-card class="state-card" data-visual=${n==="alert"?"attention":"idle"}>
      <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">Hydronicus Plant</p><h2>${t}</h2></div></div>
      <p class=${n==="alert"?"notice error":"notice"} role=${n}>${e}</p>
      ${s?a`<p class="meta">${s}</p>`:c}
    </ha-card>`}_renderLoading(t){return a`<ha-card class="loading-card" role="status" aria-busy="true">
      <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
      <div class="loading-panel"></div>
      <p class="muted">${t?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
    </ha-card>`}_renderStreamNotice(t){if(t.kind==="reconnecting"){return a`<p class="notice" role="status">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(t.kind==="retrying"){return a`<p class="notice" role="status">${t.message} Retrying in ${Math.round(t.delayMs/1e3)} s. The values below may be out of date.</p>`}return c}_renderHeader(t){const e=t.plant;const n=e.execution_boundary;const s=t.controls.requested_mode;const i=bt.includes(e.requested_mode)?bt:[...bt,e.requested_mode];return a`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${s?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>this._moreInfo(s)}>${e.name}</button>`:e.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${p(e.status)}</span>
            <span class="meta mode-detail">Requested ${p(e.requested_mode)} · active ${p(e.active_mode)}</span>
          </div>
          <p class="meta source-line"><strong>Source</strong> ${e.source.active_name??"none active"} · recommended ${e.source.recommended_name??"none"}</p>
          <p class="meta">${e.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${He(n.mode)}"><span class="visually-hidden">Execution boundary: </span>${p(n.mode)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${e.requested_mode} ?disabled=${!s} @change=${this._modeChanged}>
          ${i.map(o=>a`<option value=${o}>${p(o)}</option>`)}
        </select></label>
        ${this._renderShutdown(t)}
      </div>
    </header>`}_renderShutdown(t){const e=!t.controls.safe_shutdown;return a`<button type="button" class=${`shutdown ${this._holdingShutdown?"is-holding":""}`} ?disabled=${e} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:c}`}_renderAlerts(t){const e=It(t);if(!e.length)return c;return a`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta">${g(e.length,this._locale,0)}</span></div>${e.slice(0,3).map(n=>{const s=n.severity==="error"||n.severity==="critical";return a`<p class="alert ${s?"error":""}" data-severity=${n.severity}><strong>${p(n.code)}</strong><span> · ${n.message}</span></p>`})}</section>`}_renderZones(t){return a`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Comfort Zones</h3></div><span class="meta">${g(t.zones.length,this._locale,0)} visible</span></div><div class="zone-grid">${t.zones.length?t.zones.map(e=>this._renderZone(e)):a`<p class="muted empty-state">No visible Zones are configured for this Plant.</p>`}</div></section>`}_temperature(t,e,n){const s=this._unit;if(t===null){return a`<div class=${n}><span class="metric-value">--</span><span class="metric-label">${e}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${n}><span class="metric-value">${mt(t,s,this._locale)}</span><span class="metric-unit">${s}</span><span class="metric-label">${e}</span></div>`}_renderZone(t){const e=t.thermostat;const n=e.kind==="hydronicus";const s=t.demand||t.cooling.demand;const i=this._unit;const o=g(pt(i),this._locale,i===H?1:0);const d=e.control_entity_id;const l=Boolean(d)&&e.target_temperature!==null;return a`<article class="zone" data-phase=${t.phase} data-demand=${String(s)} data-blocked=${String(t.blocked)} aria-labelledby=${`zone-${t.id}`}>
      <div class="row"><div><h4 class="zone-title" id=${`zone-${t.id}`}>${d?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>this._moreInfo(d)}>${t.name}</button>`:t.name}</h4><p class="meta zone-owner">${n?"Hydronicus thermostat":"External thermostat \xB7 read-only"}</p></div><span class="phase ${t.blocked?"state blocked":""}">${p(t.phase)}</span></div>
      <div class="temperature-panel">
        ${this._temperature(e.current_temperature,"Current","metric")}
        ${this._temperature(e.target_temperature,"Target","metric target")}
      </div>
      <p class="meta zone-note">${s?`${t.cooling.demand?"Cooling":"Heating"} demand active`:"No demand"} · ${e.explanation}</p>
      <ul class="diagnostic-list" aria-label="Zone diagnostics">
        <li class="diagnostic-chip">${g(t.sensor_status.usable,this._locale,0)} sensor${t.sensor_status.usable===1?"":"s"} ready</li>
        ${t.sensor_status.optional_excluded?a`<li class="diagnostic-chip warning">${g(t.sensor_status.optional_excluded,this._locale,0)} optional excluded</li>`:c}
        ${t.sensor_status.required_blocking?a`<li class="diagnostic-chip danger">${g(t.sensor_status.required_blocking,this._locale,0)} required blocked</li>`:c}
        ${t.cooling.dew_point===null?c:a`<li class="diagnostic-chip">Dew point ${mt(t.cooling.dew_point,i,this._locale)} ${i}</li>`}
        ${t.cooling.condensation_margin===null?c:a`<li class="diagnostic-chip ${t.cooling.blocked?"danger":""}">Margin ${Dt(t.cooling.condensation_margin,i,this._locale)} ${i}</li>`}
      </ul>
      ${e.preset?a`<p class="meta zone-note">Preset: ${p(e.preset)}</p>`:c}
      ${t.blocked_reason?a`<p class="meta zone-note">${t.blocked_reason}</p>`:c}
      ${t.coupling_group_ids.length?a`<p class="meta coupling-note">Coupled delivery - this Zone shares hydraulic equipment.</p>`:c}
      ${n?a`<div class="zone-actions">
            <button type="button" ?disabled=${!l} aria-label=${`Decrease ${t.name} target by ${o} ${i}`} @click=${()=>this._adjustZone(t,-1)}>−${o}</button>
            <button type="button" ?disabled=${!l} aria-label=${`Increase ${t.name} target by ${o} ${i}`} @click=${()=>this._adjustZone(t,1)}>+${o}</button>
            <select class="preset" data-value=${e.preset??"none"} aria-label=${`${t.name} preset`} ?disabled=${!d} @change=${h=>this._presetChanged(t,h)}>${["none",...e.preset_modes].map(h=>a`<option value=${h}>${p(h)}</option>`)}</select>
          </div>`:a`<p class="meta">Adjust this thermostat in its owning Home Assistant integration.</p>`}
    </article>`}_renderPaths(t){if(!t.delivery_paths.length)return c;return a`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta">Zone → Circuit → Valve → Pump → Source</span></div><div class="path-list">${t.delivery_paths.map(e=>a`<article class="path" data-status=${e.status} data-flowing=${String(gt(e.status))}>
      <div class="path-head"><div class="path-heading"><strong>${t.zones.find(n=>n.id===e.zone_id)?.name??e.zone_id}</strong></div><div class="status-line"><span class="state ${e.status}">${p(e.status)}</span>${e.coupled?a`<span class="meta">coupled</span>`:c}</div></div>
      <ol class="path-track" aria-label="Ordered hydraulic delivery path">${e.nodes.map((n,s)=>a`<li class="path-step">${s?a`<span class="flow-link" aria-hidden="true"></span>`:c}<span class="node" data-kind=${n.kind} data-state=${n.state} data-flowing=${String(gt(n.state))}><span class="node-kind">${p(n.kind)}</span><span class="node-name">${n.name}</span><span class="node-state">${p(n.state)}</span></span></li>`)}</ol>
      ${e.problem?a`<p class="meta path-problem">${e.problem}</p>`:c}
    </article>`)}</div></section>`}_renderActuators(t){if(!t.actuators.length)return c;return a`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Actuator Ownership</h3></div><span class="meta">Shared consumers stay visible</span></div><div class="actuator-list">${t.actuators.map(e=>a`<article class="actuator" data-state=${e.state}><div class="row"><strong>${e.name}</strong><span class="state actuator-state ${e.state}">${p(e.state)}</span></div><p class="meta">${p(e.kind)} · ${e.reason??"No additional explanation."}</p>${e.active_consumers.length?a`<ul class="consumer-list" aria-label="Active circuit consumers">${e.active_consumers.map(n=>a`<li class="consumer-chip"><strong>${n.name}</strong> · ${n.id}</li>`)}</ul>`:a`<p class="meta zone-note">No active circuit consumers.</p>`}</article>`)}</div></section>`}_renderExplanations(t){return a`<section><details><summary>Controller explanations</summary>${t.explanations.map(e=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${p(e.scope)}</strong> · ${e.message}</p></div>`)}</details></section>`}_renderOperations(t){const e=Object.values(t.execution.operations).flat();if(!e.length)return c;return a`<section><details open><summary>Latest operation outcomes (${g(e.length,this._locale,0)})</summary>${e.map(n=>{const s=String(n.result??"unknown");return a`<div class="operation" data-result=${s}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy"><strong>${Xt(n)}</strong><br><span class="meta">${String(n.reason??n.explanation??"")}</span></p></div>`})}</details></section>`}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:t}}))}_call(t){const e=this._callService;if(!t||!e)return;e(t.domain,t.service,t.data).then(()=>{this._actionError=null},n=>{this._actionError=W(n,"The Home Assistant action failed.");this.requestUpdate()})}_dismissActionError=()=>{this._actionError=null};_modeChanged=t=>{if(!this._snapshot)return;this._call(Bt(this._snapshot,t.target.value))};_adjustZone(t,e){const n=Yt(t,e,this._unit);if(n!==null)this._call(Vt(t,n))}_presetChanged(t,e){this._call(Zt(t,e.target.value))}_startHold(){if(!this._snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;if(this._snapshot)this._call(Wt(this._snapshot))},Ce)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=t=>{if(t.button!==void 0&&t.button>0)return;this._startHold()};_keyHoldStart=t=>{if(t.key!=="Enter"&&t.key!==" ")return;t.preventDefault();if(!t.repeat)this._startHold()};_keyHoldEnd=t=>{if(t.key==="Enter"||t.key===" ")this._clearHold()};_preventContextMenu=t=>{t.preventDefault()}};if(!customElements.get(A)){customElements.define(A,X)}window.customCards=window.customCards??[];if(!window.customCards.some(r=>r.type===A)){window.customCards.push({type:A,name:"Hydronicus Plant",version:"0.1.0-rc.6",description:"Topology-driven Hydronicus Plant status and controls.",preview:true,documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
