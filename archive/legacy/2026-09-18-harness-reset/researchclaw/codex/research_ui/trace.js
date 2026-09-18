import {projectURL} from './project.js';
// Exact, selected-snapshot references. No latest-version fallback.
export function refKey(ref) {
  return ref && ['project_id','head_id','artifact_id','sha256'].every(k=>typeof ref[k]==='string')
    ? JSON.stringify(['project_id','head_id','artifact_id','sha256'].map(k=>ref[k])) : null;
}
export function resolveRef(view, ref) {
  const key=refKey(ref);
  return key ? view.artifacts.find(a=>refKey(a.ref)===key) ?? null : null;
}
export function rawURL(view, artifact) {
  if (!artifact || !view.artifacts.some(a=>a.id===artifact.id && a.raw_url===artifact.raw_url && refKey(a.ref)===refKey(artifact.ref))) return null;
  const expected=`/api/artifacts/${encodeURIComponent(artifact.id)}?head=${encodeURIComponent(view.head_id)}`;
  return /^a-[a-zA-Z0-9-]+$/.test(artifact.id) && [expected,projectURL(expected)].includes(artifact.raw_url) ? projectURL(expected) : null;
}
export function sourceURL(value) {
  try {const url=new URL(value);return ['http:','https:'].includes(url.protocol) ? url.href : null;} catch {return null;}
}
export function compareHypotheses(view,beforeId,afterId,hypothesisId) {
  const before=view.revisions.find(r=>r.record.id===beforeId),after=view.revisions.find(r=>r.record.id===afterId);
  if (!before || !after || before.record.node!=='hypothesize' || after.record.node!=='hypothesize'
      || refKey(after.previous_ref)!==refKey(before.ref)) return null;
  const a=before.record.content.hypotheses?.find(h=>h.hypothesis_id===hypothesisId);
  const b=after.record.content.hypotheses?.find(h=>h.hypothesis_id===hypothesisId);
  return a && b ? {before:a,after:b,reason:after.record.revision_reason} : null;
}
export function traceClaim(view,claimId,revisionId) {
  const revision=view.revisions.find(r=>r.record.node==='extract' && (revisionId ? r.record.id===revisionId : r.current));
  const claim=revision?.record.content.claims?.find(c=>c.claim_id===claimId);
  if (!claim) return null;
  const source=resolveRef(view,claim.source_ref);
  return {claim,revision,source,missing:source ? [] : [claim.source_ref]};
}
