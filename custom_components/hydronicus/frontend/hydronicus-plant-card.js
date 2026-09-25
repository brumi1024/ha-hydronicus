var P="hydronicus-plant-card";var G=`custom:${P}`;var pe="hydronicus/list_plants";var me=["comfortable","compact"];function Q(r){if(!r||typeof r!=="object"){throw new Error("Hydronicus Plant card requires a configuration.")}const t=r;if(t.type!==G){throw new Error(`Hydronicus Plant card type must be ${G}.`)}if(typeof t.plant!=="string"){throw new Error("Hydronicus Plant card requires one Plant UUID in `plant`.")}const e=t.density??"comfortable";if(!me.includes(e)){throw new Error("Hydronicus Plant card density must be comfortable or compact.")}return{type:G,plant:t.plant.trim(),density:e}}var J=class{plants=[];pending=null;connection=null;get known(){return this.plants}load(t){if(this.connection===t&&this.pending)return this.pending;this.connection=t;this.pending=t.sendMessagePromise({type:pe}).then(e=>{this.plants=Array.isArray(e.plants)?e.plants:[];return this.plants}).catch(()=>{if(this.connection===t)this.pending=null;return this.plants});return this.pending}async settled(t=2e3){if(!this.pending)return this.plants;let e;const n=new Promise(s=>{e=setTimeout(()=>s(this.plants),t)});try{return await Promise.race([this.pending,n])}finally{clearTimeout(e)}}reset(){this.plants=[];this.pending=null;this.connection=null}};var L=new J;async function St(r){const t=r?.connection?await L.load(r.connection):L.known;return{plant:t[0]?.id??"",density:"comfortable"}}var ge={plant:"Hydronicus Plant",density:"Density"};var fe={plant:"The Plant this card shows. Only Plants you can read are listed; one that is not listed shows its UUID.",density:"Compact uses less spacing for dense dashboards."};function be(r){if(r.length===0)return{text:{}};return{select:{mode:"dropdown",options:r.map(t=>({value:t.id,label:t.name}))}}}async function Ct(){const r=await L.settled();return{schema:[{name:"plant",required:true,selector:be(r)},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}}],computeLabel:t=>ge[t.name],computeHelper:t=>fe[t.name],assertConfig:t=>{Q(t)}}}var k=class extends Event{constructor(t,e,n,s){super("context-request",{bubbles:true,composed:true}),this.context=t,this.contextTarget=e,this.callback=n,this.subscribe=s??false}};function H(r){return r}var v=class{constructor(t,e,n,s){if(this.subscribe=false,this.provided=false,this.value=void 0,this.t=(o,i)=>{this.unsubscribe&&(this.unsubscribe!==i&&(this.provided=false,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=o,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=true,this.callback&&this.callback(o,i)),this.unsubscribe=i},this.host=t,void 0!==e.context){const o=e;this.context=o.context,this.callback=o.callback,this.subscribe=o.subscribe??false}else this.context=e,this.callback=n,this.subscribe=s??false;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new k(this.context,this.host,this.t,this.subscribe))}};var j=globalThis;var V=j.ShadowRoot&&(void 0===j.ShadyCSS||j.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype;var tt=Symbol();var At=new WeakMap;var M=class{constructor(t,e,n){if(this._$cssResult$=true,n!==tt)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(V&&void 0===t){const n=void 0!==e&&1===e.length;n&&(t=At.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),n&&At.set(e,t))}return t}toString(){return this.cssText}};var Et=r=>new M("string"==typeof r?r:r+"",void 0,tt);var et=(r,...t)=>{const e=1===r.length?r[0]:t.reduce((n,s,o)=>n+(i=>{if(true===i._$cssResult$)return i.cssText;if("number"==typeof i)return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+r[o+1],r[0]);return new M(e,r,tt)};var Pt=(r,t)=>{if(V)r.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const e of t){const n=document.createElement("style"),s=j.litNonce;void 0!==s&&n.setAttribute("nonce",s),n.textContent=e.cssText,r.appendChild(n)}};var rt=V?r=>r:r=>r instanceof CSSStyleSheet?(t=>{let e="";for(const n of t.cssRules)e+=n.cssText;return Et(e)})(r):r;var{is:ve,defineProperty:_e,getOwnPropertyDescriptor:xe,getOwnPropertyNames:$e,getOwnPropertySymbols:ke,getPrototypeOf:we}=Object;var B=globalThis;var Ht=B.trustedTypes;var Se=Ht?Ht.emptyScript:"";var Ce=B.reactiveElementPolyfillSupport;var U=(r,t)=>r;var nt={toAttribute(r,t){switch(t){case Boolean:r=r?Se:null;break;case Object:case Array:r=null==r?r:JSON.stringify(r)}return r},fromAttribute(r,t){let e=r;switch(t){case Boolean:e=null!==r;break;case Number:e=null===r?null:Number(r);break;case Object:case Array:try{e=JSON.parse(r)}catch(n){e=null}}return e}};var zt=(r,t)=>!ve(r,t);var Tt={attribute:true,type:String,converter:nt,reflect:false,useDefault:false,hasChanged:zt};Symbol.metadata??=Symbol("metadata"),B.litPropertyMetadata??=new WeakMap;var _=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=Tt){if(e.state&&(e.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=true),this.elementProperties.set(t,e),!e.noAccessor){const n=Symbol(),s=this.getPropertyDescriptor(t,n,e);void 0!==s&&_e(this.prototype,t,s)}}static getPropertyDescriptor(t,e,n){const{get:s,set:o}=xe(this.prototype,t)??{get(){return this[e]},set(i){this[e]=i}};return{get:s,set(i){const d=s?.call(this);o?.call(this,i),this.requestUpdate(t,d,n)},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??Tt}static _$Ei(){if(this.hasOwnProperty(U("elementProperties")))return;const t=we(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(U("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(U("properties"))){const e=this.properties,n=[...$e(e),...ke(e)];for(const s of n)this.createProperty(s,e[s])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[n,s]of e)this.elementProperties.set(n,s)}this._$Eh=new Map;for(const[e,n]of this.elementProperties){const s=this._$Eu(e,n);void 0!==s&&this._$Eh.set(s,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const n=new Set(t.flat(1/0).reverse());for(const s of n)e.unshift(rt(s))}else void 0!==t&&e.push(rt(t));return e}static _$Eu(t,e){const n=e.attribute;return false===n?void 0:"string"==typeof n?n:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const n of e.keys())this.hasOwnProperty(n)&&(t.set(n,this[n]),delete this[n]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Pt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,n){this._$AK(t,n)}_$ET(t,e){const n=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,n);if(void 0!==s&&true===n.reflect){const o=(void 0!==n.converter?.toAttribute?n.converter:nt).toAttribute(e,n.type);this._$Em=t,null==o?this.removeAttribute(s):this.setAttribute(s,o),this._$Em=null}}_$AK(t,e){const n=this.constructor,s=n._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const o=n.getPropertyOptions(s),i="function"==typeof o.converter?{fromAttribute:o.converter}:void 0!==o.converter?.fromAttribute?o.converter:nt;this._$Em=s;const d=i.fromAttribute(e,o.type);this[s]=d??this._$Ej?.get(s)??d,this._$Em=null}}requestUpdate(t,e,n,s=false,o){if(void 0!==t){const i=this.constructor;if(false===s&&(o=this[t]),n??=i.getPropertyOptions(t),!((n.hasChanged??zt)(o,e)||n.useDefault&&n.reflect&&o===this._$Ej?.get(t)&&!this.hasAttribute(i._$Eu(t,n))))return;this.C(t,e,n)}false===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:n,reflect:s,wrapped:o},i){n&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,i??e??this[t]),true!==o||void 0!==i)||(this._$AL.has(t)||(this.hasUpdated||n||(e=void 0),this._$AL.set(t,e)),true===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=true;try{await this._$ES}catch(e){Promise.reject(e)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[s,o]of this._$Ep)this[s]=o;this._$Ep=void 0}const n=this.constructor.elementProperties;if(n.size>0)for(const[s,o]of n){const{wrapped:i}=o,d=this[s];true!==i||this._$AL.has(s)||void 0===d||this.C(s,void 0,o,d)}}let t=false;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(e)):this._$EM()}catch(n){throw t=false,this._$EM(),n}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=false}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return true}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[U("elementProperties")]=new Map,_[U("finalized")]=new Map,Ce?.({ReactiveElement:_}),(B.reactiveElementVersions??=[]).push("2.1.2");var dt=globalThis;var Rt=r=>r;var Z=dt.trustedTypes;var Lt=Z?Z.createPolicy("lit-html",{createHTML:r=>r}):void 0;var Dt="$lit$";var x=`lit$${Math.random().toFixed(9).slice(2)}$`;var It="?"+x;var Ae=`<${It}>`;var C=document;var O=()=>C.createComment("");var N=r=>null===r||"object"!=typeof r&&"function"!=typeof r;var ut=Array.isArray;var Ee=r=>ut(r)||"function"==typeof r?.[Symbol.iterator];var st="[ 	\n\f\r]";var q=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;var Mt=/-->/g;var Ut=/>/g;var w=RegExp(`>|${st}(?:([^\\s"'>=/]+)(${st}*=${st}*(?:[^
\f\r"'\`<>=]|("|')|))|$)`,"g");var qt=/'/g;var Ot=/"/g;var Ft=/^(?:script|style|textarea|title)$/i;var ht=r=>(t,...e)=>({_$litType$:r,strings:t,values:e});var a=ht(1);var Er=ht(2);var Pr=ht(3);var A=Symbol.for("lit-noChange");var l=Symbol.for("lit-nothing");var Nt=new WeakMap;var S=C.createTreeWalker(C,129);function jt(r,t){if(!ut(r)||!r.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==Lt?Lt.createHTML(t):t}var Pe=(r,t)=>{const e=r.length-1,n=[];let s,o=2===t?"<svg>":3===t?"<math>":"",i=q;for(let d=0;d<e;d++){const c=r[d];let h,p,u=-1,g=0;for(;g<c.length&&(i.lastIndex=g,p=i.exec(c),null!==p);)g=i.lastIndex,i===q?"!--"===p[1]?i=Mt:void 0!==p[1]?i=Ut:void 0!==p[2]?(Ft.test(p[2])&&(s=RegExp("</"+p[2],"g")),i=w):void 0!==p[3]&&(i=w):i===w?">"===p[0]?(i=s??q,u=-1):void 0===p[1]?u=-2:(u=i.lastIndex-p[2].length,h=p[1],i=void 0===p[3]?w:'"'===p[3]?Ot:qt):i===Ot||i===qt?i=w:i===Mt||i===Ut?i=q:(i=w,s=void 0);const f=i===w&&r[d+1].startsWith("/>")?" ":"";o+=i===q?c+Ae:u>=0?(n.push(h),c.slice(0,u)+Dt+c.slice(u)+x+f):c+x+(-2===u?d:f)}return[jt(r,o+(r[e]||"<?>")+(2===t?"</svg>":3===t?"</math>":"")),n]};var D=class r{constructor({strings:t,_$litType$:e},n){let s;this.parts=[];let o=0,i=0;const d=t.length-1,c=this.parts,[h,p]=Pe(t,e);if(this.el=r.createElement(h,n),S.currentNode=this.el.content,2===e||3===e){const u=this.el.content.firstChild;u.replaceWith(...u.childNodes)}for(;null!==(s=S.nextNode())&&c.length<d;){if(1===s.nodeType){if(s.hasAttributes())for(const u of s.getAttributeNames())if(u.endsWith(Dt)){const g=p[i++],f=s.getAttribute(u).split(x),E=/([.?@])?(.*)/.exec(g);c.push({type:1,index:o,name:E[2],strings:f,ctor:"."===E[1]?it:"?"===E[1]?at:"@"===E[1]?ct:z}),s.removeAttribute(u)}else u.startsWith(x)&&(c.push({type:6,index:o}),s.removeAttribute(u));if(Ft.test(s.tagName)){const u=s.textContent.split(x),g=u.length-1;if(g>0){s.textContent=Z?Z.emptyScript:"";for(let f=0;f<g;f++)s.append(u[f],O()),S.nextNode(),c.push({type:2,index:++o});s.append(u[g],O())}}}else if(8===s.nodeType)if(s.data===It)c.push({type:2,index:o});else{let u=-1;for(;-1!==(u=s.data.indexOf(x,u+1));)c.push({type:7,index:o}),u+=x.length-1}o++}}static createElement(t,e){const n=C.createElement("template");return n.innerHTML=t,n}};function T(r,t,e=r,n){if(t===A)return t;let s=void 0!==n?e._$Co?.[n]:e._$Cl;const o=N(t)?void 0:t._$litDirective$;return s?.constructor!==o&&(s?._$AO?.(false),void 0===o?s=void 0:(s=new o(r),s._$AT(r,e,n)),void 0!==n?(e._$Co??=[])[n]=s:e._$Cl=s),void 0!==s&&(t=T(r,s._$AS(r,t.values),s,n)),t}var ot=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:n}=this._$AD,s=(t?.creationScope??C).importNode(e,true);S.currentNode=s;let o=S.nextNode(),i=0,d=0,c=n[0];for(;void 0!==c;){if(i===c.index){let h;2===c.type?h=new I(o,o.nextSibling,this,t):1===c.type?h=new c.ctor(o,c.name,c.strings,this,t):6===c.type&&(h=new lt(o,this,t)),this._$AV.push(h),c=n[++d]}i!==c?.index&&(o=S.nextNode(),i++)}return S.currentNode=C,s}p(t){let e=0;for(const n of this._$AV)void 0!==n&&(void 0!==n.strings?(n._$AI(t,n,e),e+=n.strings.length-2):n._$AI(t[e])),e++}};var I=class r{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,n,s){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=n,this.options=s,this._$Cv=s?.isConnected??true}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=T(this,t,e),N(t)?t===l||null==t||""===t?(this._$AH!==l&&this._$AR(),this._$AH=l):t!==this._$AH&&t!==A&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):Ee(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==l&&N(this._$AH)?this._$AA.nextSibling.data=t:this.T(C.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:n}=t,s="number"==typeof n?this._$AC(t):(void 0===n.el&&(n.el=D.createElement(jt(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===s)this._$AH.p(e);else{const o=new ot(s,this),i=o.u(this.options);o.p(e),this.T(i),this._$AH=o}}_$AC(t){let e=Nt.get(t.strings);return void 0===e&&Nt.set(t.strings,e=new D(t)),e}k(t){ut(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let n,s=0;for(const o of t)s===e.length?e.push(n=new r(this.O(O()),this.O(O()),this,this.options)):n=e[s],n._$AI(o),s++;s<e.length&&(this._$AR(n&&n._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(false,true,e);t!==this._$AB;){const n=Rt(t).nextSibling;Rt(t).remove(),t=n}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}};var z=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,n,s,o){this.type=1,this._$AH=l,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=o,n.length>2||""!==n[0]||""!==n[1]?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=l}_$AI(t,e=this,n,s){const o=this.strings;let i=false;if(void 0===o)t=T(this,t,e,0),i=!N(t)||t!==this._$AH&&t!==A,i&&(this._$AH=t);else{const d=t;let c,h;for(t=o[0],c=0;c<o.length-1;c++)h=T(this,d[n+c],e,c),h===A&&(h=this._$AH[c]),i||=!N(h)||h!==this._$AH[c],h===l?t=l:t!==l&&(t+=(h??"")+o[c+1]),this._$AH[c]=h}i&&!s&&this.j(t)}j(t){t===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}};var it=class extends z{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===l?void 0:t}};var at=class extends z{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==l)}};var ct=class extends z{constructor(t,e,n,s,o){super(t,e,n,s,o),this.type=5}_$AI(t,e=this){if((t=T(this,t,e,0)??l)===A)return;const n=this._$AH,s=t===l&&n!==l||t.capture!==n.capture||t.once!==n.once||t.passive!==n.passive,o=t!==l&&(n===l||s);s&&this.element.removeEventListener(this.name,this,n),o&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}};var lt=class{constructor(t,e,n){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(t){T(this,t)}};var He=dt.litHtmlPolyfillSupport;He?.(D,I),(dt.litHtmlVersions??=[]).push("3.3.3");var Vt=(r,t,e)=>{const n=e?.renderBefore??t;let s=n._$litPart$;if(void 0===s){const o=e?.renderBefore??null;n._$litPart$=s=new I(t.insertBefore(O(),o),o,void 0,e??{})}return s._$AI(r),s};var pt=globalThis;var $=class extends _{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Vt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false)}render(){return A}};$._$litElement$=true,$["finalized"]=true,pt.litElementHydrateSupport?.({LitElement:$});var Te=pt.litElementPolyfillSupport;Te?.({LitElement:$});(pt.litElementVersions??=[]).push("4.2.2");var R="\xB0C";var ze=5;var Re=35;function mt(r){return r?.temperature==="\xB0F"?"\xB0F":R}function W(r,t){return t==="\xB0F"?r*9/5+32:r}function Le(r,t){return t==="\xB0F"?r*9/5:r}function gt(r){return r==="\xB0F"?1:.5}function Zt(r,t,e){const n=gt(e);const s=W(r,e);const o=s/n;const i=(t>0?Math.floor(o+1e-9)+1:Math.ceil(o-1e-9)-1)*n;const d=W(ze,e);const c=W(Re,e);return Number(Math.min(c,Math.max(d,i)).toFixed(1))}function Me(r){switch(r?.number_format){case"comma_decimal":return["en-US","en"];case"decimal_comma":return["de","es","it"];case"space_comma":return["fr","sv","cs"];case"quote_decimal":return["de-CH"];case"system":return void 0;case"none":return"en-US";default:return r?.language}}var Bt=new Map;function b(r,t,e=1){const n=Me(t);const s=t?.number_format!=="none";const o=`${JSON.stringify(n)}|${e}|${s}`;let i=Bt.get(o);if(!i){try{i=new Intl.NumberFormat(n,{minimumFractionDigits:e,maximumFractionDigits:e,useGrouping:s})}catch{i=new Intl.NumberFormat(void 0,{minimumFractionDigits:e,maximumFractionDigits:e})}Bt.set(o,i)}return i.format(r)}function ft(r,t,e){return b(W(r,t),e)}function Wt(r,t,e){return b(Le(r,t),e)}var Ue=2;var qe=new Set(["active","cooling","heating","open","opening","overrun","ready","requested","running","selected","starting","waiting"]);function Kt(r){if(!r||typeof r!=="object"){throw new Error("Hydronicus returned no Plant snapshot.")}const t=r;if(t.schema_version!==Ue){throw new Error(`Unsupported Hydronicus snapshot schema: ${String(t.schema_version)}.`)}if(!t.plant||!Array.isArray(t.zones)||!Array.isArray(t.alerts)){throw new Error("Hydronicus returned an incomplete Plant snapshot.")}return t}function Xt(r){return[...r.alerts].sort((t,e)=>t.priority-e.priority||t.code.localeCompare(e.code)||t.scope.localeCompare(e.scope))}function Yt(r){const t=r.plant.health.toLowerCase();const e=r.alerts.some(s=>s.severity==="critical"||s.severity==="error");if(r.safe_shutdown.active||e||["blocked","critical","error","failed","unhealthy"].includes(t)){return"attention"}const n=`${r.plant.active_mode} ${r.plant.status}`.toLowerCase();if(n.includes("cool"))return"cooling";if(n.includes("heat"))return"heating";return"idle"}function bt(r){return qe.has(r.toLowerCase())}function Gt(r,t){if(r.thermostat.kind!=="hydronicus"||!r.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_temperature",data:{entity_id:r.thermostat.control_entity_id,temperature:t}}}function Jt(r,t){if(r.thermostat.kind!=="hydronicus"||!r.thermostat.control_entity_id)return null;return{domain:"climate",service:"set_preset_mode",data:{entity_id:r.thermostat.control_entity_id,preset_mode:t}}}function Qt(r,t){if(r.thermostat.kind!=="hydronicus"||!r.thermostat.control_entity_id)return null;if(!vt(r).includes(t))return null;return{domain:"climate",service:"set_hvac_mode",data:{entity_id:r.thermostat.control_entity_id,hvac_mode:t}}}function te(r,t){if(!r.controls.requested_mode)return null;return{domain:"select",service:"select_option",data:{entity_id:r.controls.requested_mode,option:t}}}function ee(r){if(!r.controls.safe_shutdown)return null;return{domain:"button",service:"press",data:{entity_id:r.controls.safe_shutdown}}}function re(r){const t=String(r.action??"operation").replaceAll("_"," ");const e=String(r.actuator_name??"actuator");const n=String(r.result??"");if(n==="proposed")return`Would ${t} ${e}`;if(n==="executed")return`Executed ${e} ${t}`;if(n==="suppressed")return`Suppressed ${e} ${t}`;return`${n||"Operation"}: ${e} ${t}`}function Oe(r){return r.replaceAll("_"," ")}function F(r,t,e){const[n,s]=t.split(".");return r?.(`component.hydronicus.entity.${n}.${s}.state.${e}`)||m(e)}function m(r){const t=Oe(r);return t.charAt(0).toUpperCase()+t.slice(1)}var Ne={off:"Off",heat:"Heat",cool:"Cool",heat_cool:"Heat/Cool",auto:"Auto"};function yt(r,t){return r?.(`component.climate.entity_component._.state.${t}`)||Ne[t]||m(t)}function vt(r){if(r.thermostat.kind!=="hydronicus")return[];return[...new Set(r.thermostat.hvac_modes??[])]}function _t(r){if(r.dry_run||r.mode==="dry_run")return"Dry run";if(r.mode==="mixed"&&!r.forced_shadow.length)return"Live";return m(r.mode)}function ne(r){if(r.dry_run||r.mode==="dry_run")return"dry-run";if(r.mode==="mixed"&&!r.forced_shadow.length)return"live";return r.mode.replaceAll("_","-")}function se(r){const{active_name:t,recommended_name:e}=r.plant.source;if(!r.sources.length&&!t&&!e)return null;const n=[t??"None active"];if(e&&e!==t)n.push(`recommended ${e}`);return n.join(" \xB7 ")}var De={zone:"Room",circuit:"Loop"};function xt(r){return De[r]??m(r)}function oe(r){return[...new Set(r.thermostat.preset_modes)].filter(t=>t!=="none")}function ie(r,t,e=R){if(r.thermostat.target_temperature===null)return null;return Zt(r.thermostat.target_temperature,t,e)}var Ie="hydronicus/subscribe_plant";var Fe=1e3;var je=6e4;var Ve={setTimeout:(r,t)=>globalThis.setTimeout(r,t),clearTimeout:r=>globalThis.clearTimeout(r)};var ae={plant_not_found:"not_found",unauthorized:"unauthorized"};function ce(r){return r!==void 0&&Object.hasOwn(ae,r)?ae[r]:void 0}function Be(r){return typeof r==="object"&&r!==null&&"code"in r?String(r.code):void 0}function X(r,t){if(r instanceof Error)return r.message;if(typeof r==="object"&&r!==null&&"message"in r&&r.message){return String(r.message)}return t}function $t(r){if(!r)return;try{void Promise.resolve(r()).catch(()=>void 0)}catch{}}var K=class{constructor(t,e=Ve){this.host=t;this.scheduler=e}host;scheduler;connection;plantId;generation=0;unsubscribe;retryHandle;attempt=0;current={kind:"idle"};get status(){return this.current}connect(t,e){if(t===this.connection&&e===this.plantId)return;this.disconnect();if(!t||!e)return;this.connection=t;this.plantId=e;t.addEventListener?.("disconnected",this.handleDisconnected);t.addEventListener?.("ready",this.handleReady);this.subscribe()}disconnect(){this.cancelRetry();this.generation+=1;$t(this.unsubscribe);this.unsubscribe=void 0;this.connection?.removeEventListener?.("disconnected",this.handleDisconnected);this.connection?.removeEventListener?.("ready",this.handleReady);this.connection=void 0;this.plantId=void 0;this.attempt=0;this.setStatus({kind:"idle"})}subscribe(){const t=this.connection;const e=this.plantId;if(!t||!e)return;this.cancelRetry();const n=++this.generation;if(this.current.kind!=="reconnecting"&&this.current.kind!=="retrying"){this.setStatus({kind:"connecting"})}t.subscribeMessage(s=>this.handleEvent(n,s),{type:Ie,plant_id:e},{resubscribe:false}).then(s=>{if(n!==this.generation){$t(s);return}this.unsubscribe=s}).catch(s=>{if(n!==this.generation)return;this.handleError(s)})}handleEvent(t,e){if(t!==this.generation)return;if(e.snapshot!==void 0&&e.snapshot!==null){this.attempt=0;this.setStatus({kind:"live"});this.host.onSnapshot(e.snapshot);return}if(e.status==="unavailable"){this.setStatus({kind:"unavailable"});return}const n=ce(e.status);if(n)this.stop({kind:n})}handleError(t){const e=ce(Be(t));if(e){this.stop({kind:e});return}const n=Math.min(Fe*2**this.attempt,je);this.attempt+=1;this.setStatus({kind:"retrying",attempt:this.attempt,delayMs:n,message:X(t,"The Hydronicus Plant stream failed.")});this.retryHandle=this.scheduler.setTimeout(()=>{this.retryHandle=void 0;this.subscribe()},n)}stop(t){this.cancelRetry();this.generation+=1;$t(this.unsubscribe);this.unsubscribe=void 0;this.setStatus(t)}handleDisconnected=()=>{this.cancelRetry();this.generation+=1;this.unsubscribe=void 0;this.setStatus({kind:"reconnecting"})};handleReady=()=>{this.attempt=0;this.subscribe()};cancelRetry(){if(this.retryHandle!==void 0)this.scheduler.clearTimeout(this.retryHandle);this.retryHandle=void 0}setStatus(t){this.current=t;this.host.onStatus(t)}};var le=et`
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
`;var kt=["auto","idle","heating","cooling"];var Ze=1200;var We=H("hassConnection");var Ke=H("hassApi");var Xe=H("hassConfig");var Ye=H("hassInternationalization");function de(r){return`Retrying in ${Math.round(r/1e3)} s.`}var Y=class extends ${static properties={preview:{type:Boolean},_config:{state:true},_connection:{state:true},_unit:{state:true},_locale:{state:true},_localize:{state:true},_snapshot:{state:true},_snapshotError:{state:true},_stream:{state:true},_actionError:{state:true},_holdingShutdown:{state:true}};static styles=le;_hass;_callService;_fromContext=new Set;_plantStream;_holdTimer=null;constructor(){super();this.preview=false;this._config=void 0;this._connection=void 0;this._unit=R;this._locale=void 0;this._localize=void 0;this._snapshot=null;this._snapshotError=null;this._stream={kind:"idle"};this._actionError=null;this._holdingShutdown=false;this._plantStream=new K({onStatus:t=>this._streamStatusChanged(t),onSnapshot:t=>this._snapshotReceived(t)});new v(this,{context:We,subscribe:true,callback:t=>{this._fromContext.add("connection");this._connection=t?.connection}});new v(this,{context:Ke,subscribe:true,callback:t=>{this._fromContext.add("api");this._callService=t?.callService}});new v(this,{context:Xe,subscribe:true,callback:t=>{this._fromContext.add("config");this._unit=mt(t?.config?.unit_system)}});new v(this,{context:Ye,subscribe:true,callback:t=>{this._fromContext.add("i18n");this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}})}set hass(t){this._hass=t;if(!this._fromContext.has("connection"))this._connection=t?.connection;if(!this._fromContext.has("api"))this._callService=t?(...e)=>t.callService(...e):void 0;if(!this._fromContext.has("config"))this._unit=mt(t?.config?.unit_system);if(!this._fromContext.has("i18n")){this._locale=t?.locale??(t?.language?{language:t.language}:void 0);this._localize=t?.localize}}get hass(){return this._hass}static async getConfigForm(){return Ct()}static async getStubConfig(t){return St(t)}setConfig(t){const e=Q(t);if(e.plant!==this._config?.plant){this._snapshot=null;this._snapshotError=null;this._actionError=null}this._config=e}getCardSize(){const t=this._snapshot;if(!t)return 4;let e=4;const n=Math.min(t.alerts.length,3);if(n)e+=1+n;e+=1+Math.max(1,t.zones.length)*5;if(t.delivery_paths.length)e+=1+t.delivery_paths.length*3;if(t.actuators.length)e+=1+t.actuators.length*2;e+=1;const s=Object.values(t.execution.operations).flat().length;if(s)e+=1+s;return e}getGridOptions(){return{columns:12,min_columns:6}}connectedCallback(){super.connectedCallback();this.requestUpdate()}disconnectedCallback(){this._plantStream.disconnect();this._clearHold();super.disconnectedCallback()}updated(t){super.updated(t);this._syncSelectValues();if(!this.isConnected)return;const e=this._config?.plant||void 0;this._plantStream.connect(this._connection,e);if(this._connection&&(t.has("_connection")||this.preview))void L.load(this._connection)}_syncSelectValues(){for(const t of this.renderRoot.querySelectorAll("select[data-value]")){const e=t.dataset.value??"";if(t.value!==e)t.value=e}}_streamStatusChanged(t){this._stream=t;if(["idle","unavailable","not_found","unauthorized"].includes(t.kind)){this._snapshot=null;this._clearHold()}}_snapshotReceived(t){try{this._snapshot=Kt(t);this._snapshotError=null}catch(e){this._snapshot=null;this._snapshotError=X(e,"Unsupported Hydronicus snapshot.")}}render(){const t=this._config;if(!t||!t.plant){return this._renderState("Hydronicus Plant","Select a Hydronicus Plant in the card editor.","status")}if(this._snapshotError){return this._renderState("Card update needed",this._snapshotError,"alert","Reload the browser after upgrading Hydronicus so the card and the integration match.")}const e=this._snapshot;const n=this._stream;if(!e){switch(n.kind){case"not_found":return this._renderState("Plant not found","This Hydronicus Plant was not found. Choose another Plant in the card editor.","alert");case"unauthorized":return this._renderState("No access","You do not have access to this Hydronicus Plant.","alert");case"unavailable":return this._renderState("Plant unavailable","The Hydronicus Plant is unavailable while it loads or after it was unloaded. The card reconnects automatically.","status");case"retrying":return this._renderState("Connection needs attention",n.message,"alert",de(n.delayMs));default:return this._renderLoading(n.kind==="reconnecting")}}return a`<ha-card class=${t.density??"comfortable"} data-visual=${Yt(e)}>
      ${this._renderHeader(e)}
      ${this._renderStreamNotice(n)}
      ${this._actionError?a`<div class="action-error" role="alert"><span dir="auto">${this._actionError}</span><button type="button" @click=${this._dismissActionError}>Dismiss</button></div>`:l}
      <div class="boundary" role="status">
        <span class="boundary-orb" aria-hidden="true"></span>
        <p class="boundary-copy" dir="auto"><span class="control-label">Execution boundary</span><strong>${e.plant.execution_boundary.message||`${_t(e.plant.execution_boundary)} execution boundary is active.`}</strong></p>
      </div>
      ${this._renderAlerts(e)}
      ${this._renderZones(e)}
      ${this._renderPaths(e)}
      ${this._renderActuators(e)}
      ${this._renderExplanations(e)}
      ${this._renderOperations(e)}
    </ha-card>`}_renderState(t,e,n,s){return a`<ha-card class="state-card" data-visual=${n==="alert"?"attention":"idle"}>
      <div class="plant-heading"><span class="plant-mark" aria-hidden="true"></span><div><p class="eyebrow">Hydronicus Plant</p><h2>${t}</h2></div></div>
      <p class=${n==="alert"?"notice error":"notice"} role=${n} dir="auto">${e}</p>
      ${s?a`<p class="meta" dir="auto">${s}</p>`:l}
    </ha-card>`}_renderLoading(t){return a`<ha-card class="loading-card" role="status" aria-busy="true">
      <div class="loading-head"><span class="loading-mark" aria-hidden="true"></span><div><div class="skeleton"></div><div class="skeleton short"></div></div></div>
      <div class="loading-panel"></div>
      <p class="muted">${t?"Reconnecting to Home Assistant\u2026":"Loading Plant snapshot\u2026"}</p>
    </ha-card>`}_renderStreamNotice(t){if(t.kind==="reconnecting"){return a`<p class="notice" role="status" dir="auto">Reconnecting to Home Assistant… The values below may be out of date.</p>`}if(t.kind==="retrying"){return a`<p class="notice" role="status" dir="auto">${t.message} ${de(t.delayMs)} The values below may be out of date.</p>`}return l}_renderHeader(t){const e=t.plant;const n=e.execution_boundary;const s=t.controls.requested_mode;const o=kt.includes(e.requested_mode)?kt:[...kt,e.requested_mode];const i=se(t);return a`<header class="header">
      <div class="plant-heading">
        <span class="plant-mark" aria-hidden="true"></span>
        <div class="header-copy">
          <p class="eyebrow">Hydronicus Plant</p>
          <h2 class="plant-title">${s?a`<button type="button" class="link" aria-haspopup="dialog" title="Show Plant mode details" @click=${()=>this._moreInfo(s)}>${e.name}</button>`:e.name}</h2>
          <div class="status-line">
            <span class="status-primary"><span class="status-dot" aria-hidden="true"></span>${F(this._localize,"sensor.controller_status",e.status)}</span>
            <span class="meta mode-detail">${this._modeDetail(t)}</span>
          </div>
          ${i===null?l:a`<p class="meta source-line" dir="auto"><strong>Source</strong> ${i}</p>`}
          <p class="meta" dir="auto">${e.controller.mode_explanation||"The controller is starting."}</p>
        </div>
      </div>
      <div class="controls">
        <span class="badge ${ne(n)}"><span class="visually-hidden">Execution boundary: </span>${_t(n)}</span>
        <label class="mode-control"><span class="control-label">Mode</span><select aria-label="Requested Plant mode" data-value=${e.requested_mode} ?disabled=${!s} @change=${this._modeChanged}>
          ${o.map(d=>a`<option value=${d}>${F(this._localize,"select.requested_mode",d)}</option>`)}
        </select></label>
        ${this._renderShutdown(t)}
      </div>
    </header>`}_modeDetail(t){const e=t.plant;const n=`Mode ${F(this._localize,"select.requested_mode",e.requested_mode)}`;if(e.requested_mode==="auto"||e.requested_mode===e.active_mode)return n;return`${n} \xB7 now ${F(this._localize,"sensor.operating_mode",e.active_mode)}`}_renderShutdown(t){const e=!t.controls.safe_shutdown;const n=t.plant.execution_boundary.dry_run;return a`<button type="button" class=${`shutdown${n?" quiet":""}${this._holdingShutdown?" is-holding":""}`} ?disabled=${e} aria-describedby="shutdown-hint"
        @pointerdown=${this._pointerHoldStart} @pointerup=${this._clearHold} @pointerleave=${this._clearHold} @pointercancel=${this._clearHold} @lostpointercapture=${this._clearHold}
        @keydown=${this._keyHoldStart} @keyup=${this._keyHoldEnd} @blur=${this._clearHold} @contextmenu=${this._preventContextMenu}>
        <span class="button-label">Safe shutdown</span>
      </button>
      <span id="shutdown-hint" class="visually-hidden">Press and hold for 1.2 seconds to confirm.</span>
      ${this._holdingShutdown?a`<span class="hold-progress" role="status">Keep holding…</span>`:l}`}_renderAlerts(t){const e=Xt(t);if(!e.length)return l;return a`<section aria-labelledby="hydronicus-alerts"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-alerts">Alerts</h3></div><span class="meta" dir="auto">${b(e.length,this._locale,0)}</span></div>${e.slice(0,3).map(n=>{const s=n.severity==="error"||n.severity==="critical";return a`<p class="alert ${s?"error":""}" data-severity=${n.severity} dir="auto"><strong>${m(n.code)}</strong><span> · ${n.message}</span></p>`})}</section>`}_renderZones(t){return a`<section aria-labelledby="hydronicus-zones"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-zones">Rooms</h3></div><span class="meta" dir="auto">${b(t.zones.length,this._locale,0)} visible</span></div><div class="zone-grid">${t.zones.length?t.zones.map(e=>this._renderZone(e)):a`<p class="muted empty-state" dir="auto">No Rooms are visible for this Plant.</p>`}</div></section>`}_temperature(t,e,n){const s=this._unit;if(t===null){return a`<div class=${n}><span class="metric-value">--</span><span class="metric-label">${e}<span class="visually-hidden"> unavailable</span></span></div>`}return a`<div class=${n}><span class="metric-value">${ft(t,s,this._locale)}</span><span class="metric-unit">${s}</span><span class="metric-label">${e}</span></div>`}_renderZone(t){const e=t.thermostat;const n=e.kind==="hydronicus";const s=t.cooling.demand?"cooling":t.demand?"heating":"none";const o=s!=="none";const i=e.hvac_mode==="off";const d=this._unit;const c=b(gt(d),this._locale,d===R?1:0);const h=e.control_entity_id;const p=Boolean(h)&&e.target_temperature!==null;const u=oe(t);const g=vt(t);const f=e.hvac_mode?yt(this._localize,e.hvac_mode):null;const E=i&&!t.blocked?f??"Off":m(t.phase);const wt=o?`${s==="cooling"?"Cooling":"Heating"} demand active`:i?"Thermostat off":"No demand";return a`<article class="zone" data-phase=${t.phase} data-hvac-mode=${e.hvac_mode??"unknown"} data-demand=${String(o)} data-demand-kind=${s} data-blocked=${String(t.blocked)} aria-labelledby=${`zone-${t.id}`}>
      <div class="row"><div><h4 class="zone-title" id=${`zone-${t.id}`}>${h?a`<button type="button" class="link" aria-haspopup="dialog" title="Show thermostat details" @click=${()=>this._moreInfo(h)}>${t.name}</button>`:t.name}</h4><p class="meta zone-owner">${n?"Hydronicus thermostat":`External thermostat \xB7 read-only${f?` \xB7 ${f}`:""}`}</p></div><span class=${`phase${t.blocked?" state blocked":""}${i?" off":""}`}>${E}</span></div>
      <div class="temperature-panel">
        ${this._temperature(e.current_temperature,"Current","metric")}
        ${this._temperature(e.target_temperature,"Target","metric target")}
      </div>
      <p class="meta zone-note" dir="auto">${n?wt:`${wt} \xB7 ${e.explanation}`}</p>
      <ul class="diagnostic-list" aria-label="Room diagnostics">
        <li class="diagnostic-chip" dir="auto">${b(t.sensor_status.usable,this._locale,0)} sensor${t.sensor_status.usable===1?"":"s"} ready</li>
        ${t.sensor_status.optional_excluded?a`<li class="diagnostic-chip warning" dir="auto">${b(t.sensor_status.optional_excluded,this._locale,0)} optional excluded</li>`:l}
        ${t.sensor_status.required_blocking?a`<li class="diagnostic-chip danger" dir="auto">${b(t.sensor_status.required_blocking,this._locale,0)} required blocked</li>`:l}
        ${t.cooling.dew_point===null?l:a`<li class="diagnostic-chip" dir="auto">Dew point ${ft(t.cooling.dew_point,d,this._locale)} ${d}</li>`}
        ${t.cooling.condensation_margin===null?l:a`<li class="diagnostic-chip ${t.cooling.blocked?"danger":""}" dir="auto">Margin ${Wt(t.cooling.condensation_margin,d,this._locale)} ${d}</li>`}
      </ul>
      ${e.preset&&e.preset!=="none"?a`<p class="meta zone-note" dir="auto">Preset: ${m(e.preset)}</p>`:l}
      ${t.blocked_reason?a`<p class="meta zone-note" dir="auto">${t.blocked_reason}</p>`:l}
      ${t.coupling_group_ids.length?a`<p class="meta coupling-note" dir="auto">Coupled delivery - this Room shares hydraulic equipment.</p>`:l}
      ${n?a`${g.length?a`<div class="hvac-modes" role="group" aria-label=${`${t.name} HVAC mode`}>${g.map(y=>a`<button type="button" class="hvac-mode" data-mode=${y} aria-pressed=${String(y===e.hvac_mode)} ?disabled=${!h} @click=${()=>this._hvacModeChosen(t,y)}>${yt(this._localize,y)}</button>`)}</div>`:l}
            <div class="zone-actions">
              <button type="button" dir="ltr" ?disabled=${!p} aria-label=${`Decrease ${t.name} target by ${c} ${d}`} @click=${()=>this._adjustZone(t,-1)}>−${c}</button>
              <button type="button" dir="ltr" ?disabled=${!p} aria-label=${`Increase ${t.name} target by ${c} ${d}`} @click=${()=>this._adjustZone(t,1)}>+${c}</button>
              ${u.length?a`<select class="preset" data-value=${e.preset??"none"} aria-label=${`${t.name} preset`} ?disabled=${!h} @change=${y=>this._presetChanged(t,y)}>${["none",...u].map(y=>a`<option value=${y}>${m(y)}</option>`)}</select>`:l}
            </div>`:a`<p class="meta" dir="auto">Adjust this thermostat in its owning Home Assistant integration.</p>`}
    </article>`}_renderPaths(t){if(!t.delivery_paths.length)return l;return a`<section aria-labelledby="hydronicus-paths"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-paths">Hydraulic Flow</h3></div><span class="meta" dir="auto">Room → Loop → Valve → Pump → Source</span></div><div class="path-list">${t.delivery_paths.map(e=>a`<article class="path" data-status=${e.status} data-flowing=${String(bt(e.status))}>
      <div class="path-head"><div class="path-heading"><strong>${t.zones.find(n=>n.id===e.zone_id)?.name??e.zone_id}</strong></div><div class="status-line"><span class="state ${e.status}">${m(e.status)}</span>${e.coupled?a`<span class="meta">shares equipment</span>`:l}</div></div>
      <ol class="path-track" aria-label="Ordered hydraulic delivery path">${e.nodes.map((n,s)=>a`<li class="path-step">${s?a`<span class="flow-link" aria-hidden="true"></span>`:l}<span class="node" data-kind=${n.kind} data-state=${n.state} data-flowing=${String(bt(n.state))}><span class="node-kind">${xt(n.kind)}</span><span class="node-name">${n.name}</span><span class="node-state">${m(n.state)}</span></span></li>`)}</ol>
      ${e.problem?a`<p class="meta path-problem" dir="auto">${e.problem}</p>`:l}
    </article>`)}</div></section>`}_renderActuators(t){if(!t.actuators.length)return l;return a`<section aria-labelledby="hydronicus-actuators"><div class="section-head"><div class="section-kicker"><h3 id="hydronicus-actuators">Equipment</h3></div><span class="meta" dir="auto">Loops using each valve and pump</span></div><div class="actuator-list">${t.actuators.map(e=>a`<article class="actuator" data-state=${e.state}><div class="row"><strong>${e.name}</strong><span class="state actuator-state ${e.state}">${m(e.state)}</span></div><p class="meta" dir="auto">${m(e.kind)} · ${e.reason??"No additional explanation."}</p>${e.active_consumers.length?a`<ul class="consumer-list" aria-label="Loops using this equipment">${e.active_consumers.map(n=>a`<li class="consumer-chip" title=${n.id}><strong>${n.name}</strong></li>`)}</ul>`:a`<p class="meta zone-note" dir="auto">No loop is using this right now.</p>`}</article>`)}</div></section>`}_renderExplanations(t){return a`<section><details><summary>Controller explanations</summary>${t.explanations.map(e=>a`<div class="operation"><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${xt(e.scope)}</strong> · ${e.message}</p></div>`)}</details></section>`}_renderOperations(t){const e=Object.values(t.execution.operations).flat();if(!e.length)return l;return a`<section><details open><summary>Latest operation outcomes (${b(e.length,this._locale,0)})</summary>${e.map(n=>{const s=String(n.result??"unknown");return a`<div class="operation" data-result=${s}><span class="operation-marker" aria-hidden="true"></span><p class="operation-copy" dir="auto"><strong>${re(n)}</strong><br><span class="meta">${String(n.reason??n.explanation??"")}</span></p></div>`})}</details></section>`}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:true,composed:true,detail:{entityId:t}}))}_call(t){const e=this._callService;if(!t||!e)return;e(t.domain,t.service,t.data,void 0,false).then(()=>{this._actionError=null},n=>{this._actionError=X(n,"The Home Assistant action failed.");this.requestUpdate()})}_dismissActionError=()=>{this._actionError=null};_modeChanged=t=>{if(!this._snapshot)return;this._call(te(this._snapshot,t.target.value))};_adjustZone(t,e){const n=ie(t,e,this._unit);if(n!==null)this._call(Gt(t,n))}_hvacModeChosen(t,e){if(e===t.thermostat.hvac_mode)return;this._call(Qt(t,e))}_presetChanged(t,e){this._call(Jt(t,e.target.value))}_startHold(){if(!this._snapshot||this._holdTimer!==null)return;this._holdingShutdown=true;this._holdTimer=setTimeout(()=>{this._holdTimer=null;this._holdingShutdown=false;if(this._snapshot)this._call(ee(this._snapshot))},Ze)}_clearHold=()=>{if(this._holdTimer!==null)clearTimeout(this._holdTimer);this._holdTimer=null;this._holdingShutdown=false};_pointerHoldStart=t=>{if(t.button!==void 0&&t.button>0)return;this._startHold()};_keyHoldStart=t=>{if(t.key!=="Enter"&&t.key!==" ")return;t.preventDefault();if(!t.repeat)this._startHold()};_keyHoldEnd=t=>{if(t.key==="Enter"||t.key===" ")this._clearHold()};_preventContextMenu=t=>{t.preventDefault()}};function ue(r){if(!r.get(P))r.define(P,Y)}var he=window.customElements;ue(he);void he.whenDefined("home-assistant").then(()=>{ue(window.customElements)});window.customCards=window.customCards??[];if(!window.customCards.some(r=>r.type===P)){window.customCards.push({type:P,name:"Hydronicus Plant",version:"0.1.0-rc.6",description:"Topology-driven Hydronicus Plant status and controls.",preview:true,documentationURL:"https://github.com/brumi1024/ha-hydronicus/blob/main/docs/lovelace.md"})}
