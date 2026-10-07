'use strict';
// Display names only: never rewrite candidate IDs, ranks, inputs or checkpoints.
window.AF3_NAMES = {
  context(run, synthetic=false) {
    if(run.af3_naming)return {...run.af3_naming,synthetic};
    const t=run.target||{},h=/^([ABC])_(minibinder|short_peptide)$/.exec(run.branch||'');
    const base=h?'sr56_'+h[1].toLowerCase()+'_helix'+(h[1]==='A'?32:45)+'_'+h[2]+'_large256_refine_v'+(h[1]==='A'&&h[2]==='minibinder'?3:4)+'_20261002_chain_terminal_oxt_v1_20261004':null;
    const suffixes=['','_output_v1_20261007','_output_v1_20261007_compact_v2_20261007','_output_v1_20261007_compact_v2_20261007_layout_v3'];
    const bounds=h?{A:[6646,6677],B:[6676,6720],C:[6717,6761]}[h[1]]:null;
    if(h&&suffixes.some(s=>run.namespace===base+s)&&JSON.stringify(t.canonical_range)===JSON.stringify(bounds))return {protein:'nesprin-2G',region:'SR56',helix:h[1]+'-helix',uniprot:'Q6ZWQ0',residue_range:t.canonical_range,mode:run.config?.design_task||'binder',synthetic};
    const mapping=t.residue_mapping||[],range=t.source_residue_range||(mapping.length?[mapping[0].source_res_id,mapping.at(-1).source_res_id]:null);
    return {protein:t.label||'待填蛋白',region:t.region||'待填区域',helix:t.helix||'',uniprot:t.uniprot||'待填UniProt',residue_range:range?'author:'+t.source_chain+':'+range.join('-'):'待填残基号',mode:run.config?.design_task||'待填模式',synthetic};
  },
  format(context, candidate, rank) {
    const t=context||{},range=Array.isArray(t.residue_range)?t.residue_range.join('-'):t.residue_range||'待填残基号';
    const value=typeof rank==='string'&&/^[1-9]\d*$/.test(rank)?Number(rank):rank;
    const number=Number.isSafeInteger(value)&&value>0?'rank'+value:'unranked';
    return [t.synthetic?'SYNTHETIC':'',t.protein||'待填蛋白',t.region||'待填区域',t.helix||'',t.uniprot||'待填UniProt',range,(t.mode||'待填模式')+'-'+number+'-'+candidate].filter(Boolean).join(' ');
  },
  async copy(button) {
    const value=button.dataset.af3Name;
    try {
      if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(value);
      else {
        const field=document.createElement('textarea');field.value=value;field.style.position='fixed';field.style.opacity='0';document.body.appendChild(field);field.select();
        const ok=document.execCommand('copy');field.remove();if(!ok)throw Error('Clipboard unavailable');
      }
      button.textContent='已复制 AF3 名称';
    } catch (_) {button.textContent='请选中上方名称复制';}
  }
};
