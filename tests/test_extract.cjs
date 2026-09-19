const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('vivo/extract.js', 'utf8');
function extract(root, id) {
  const context = {document: {querySelectorAll: () => [{__vue__: root}]}};
  return vm.runInNewContext('(' + source + ')', context)(id);
}
const location = {time: 1788690000000, latitude: 33, longitude: 107, locationDesc: 'fixture'};
const root = {$store: {getters: {'device/selected': {id:'phone-1', location}}}, $children: []};
assert.equal(extract(root, 'phone-1').timestamp, 1788690000);
assert.equal(extract(root, 'phone-1').accuracy, null);
assert.equal(extract(root, 'phone-1').crs, 'BD09');
assert.equal(extract(root, 'another-phone'), null);
assert.throws(() => extract(root, ''), /Missing app or device binding/);
const oldRoot = {$children:[{$options:{name:'Bound'}, targetDevice:{id:'phone-1'}, locationStatus:'locateSuccess', position:location}]};
assert.equal(extract(oldRoot, 'phone-1').source, 'Bound.position');
oldRoot.$children[0].locationStatus = 'loading';
assert.equal(extract(oldRoot, 'phone-1'), null);
const shared = {$store: {state:{share:{componentName:'ShareDetail',familyOpenid:'member-1',shareInfoObj:{shareInfo:{sharedBy:2},lastLocation:{...location,ctime:location.time}}}}},$children:[]};
assert.equal(extract(shared, 'share:member-1').timestamp, 1788690000);
assert.equal(extract(shared, 'share:other'), null);
shared.$store.state.share.shareInfoObj.shareInfo.sharedBy = 0;
assert.equal(extract(shared, 'share:member-1'), null);
console.log('Adapter fixture tests passed (not live verification)');
