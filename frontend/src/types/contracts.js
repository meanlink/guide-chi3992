/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,revisions:Object<string,number>,supplement_count:number,supplements?:Array<SupplementLog>}} Dataset */
/** @typedef {{id:number,dataset_id:number,source:string,status:'applied'|'rejected',summary:Reconciliation,created_by:string,created_at:number,uploaded_count:number}} SupplementLog */
/** @typedef {{total:number,added:number,corrected:number,ignored:number,conflict:number,ok:boolean,items:Array<{line:number,record:string,revision:number,outcome:'added'|'corrected'|'ignored'|'conflict',reason:string}>,conflicts:Array}} Reconciliation */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,records_snapshot:Array}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
