/* FieldKey search helpers: tidy what voice dictation hears, and match addresses however the
   street type is written ("Main Street" finds "123 MAIN ST" and the other way round).
   Tests: node --test tests/ */
(function(root, factory){
  if(typeof module==="object"&&module.exports) module.exports=factory(); else root.FKSearch=factory();
})(this, function(){
  const DIGIT_WORDS={zero:"0",oh:"0",o:"0",one:"1",two:"2",three:"3",four:"4",five:"5",six:"6",seven:"7",eight:"8",nine:"9"};
  // words people say before a number; dropped when the rest is all digits
  const PREFIX_WORDS=new Set(["sap","s","a","p","id","phone","number","no","pole"]);

  /* What the speech engine wrote -> what goes in the search box.
     "123 456 789." -> "123456789"; "SAP 1 2 3..." -> "123..."; "five three oh, five five five" -> "530555";
     anything else just loses the punctuation the engine adds at the ends ("Main Street." -> "Main Street"). */
  function spokenToQuery(text){
    const t=String(text||"").trim().replace(/^[\s.,!?;:]+|[\s.,!?;:]+$/g,"");
    const words=t.toLowerCase().split(/[\s,.\-()/]+/).filter(Boolean);
    let i=0;
    while(i<words.length&&PREFIX_WORDS.has(words[i])) i++;
    const rest=words.slice(i);
    // a lone number word ("oh", "five") stays a word; two or more, or real digits, are a number
    if(rest.length&&rest.every(w=>/^\d+$/.test(w)||DIGIT_WORDS[w])&&(rest.length>1||/^\d+$/.test(rest[0]))){
      return rest.map(w=>DIGIT_WORDS[w]||w).join("");
    }
    return t;
  }

  const WORD_FORMS={
    street:"st",avenue:"ave",av:"ave",road:"rd",drive:"dr",lane:"ln",court:"ct",boulevard:"blvd",place:"pl",
    circle:"cir",highway:"hwy",parkway:"pkwy",terrace:"ter",trail:"trl",square:"sq",mount:"mt",
    north:"n",south:"s",east:"e",west:"w",northeast:"ne",northwest:"nw",southeast:"se",southwest:"sw",
    first:"1st",second:"2nd",third:"3rd",fourth:"4th",fifth:"5th",sixth:"6th",seventh:"7th",eighth:"8th",ninth:"9th",tenth:"10th"
  };
  /* Lower case, punctuation gone, each word in one standard short form. */
  function searchKey(text){
    return String(text||"").toLowerCase().replace(/[^a-z0-9\s]+/g," ").split(/\s+/).filter(Boolean)
      .map(w=>WORD_FORMS[w]||w).join(" ");
  }
  /* Whole words of the query, in order, somewhere in the text: "123 main street" in "123 Main St, Redding".
     Whole words only, so "west" (-> "w") finds "W Cypress Ave" but not "Walnut". */
  function wordsMatch(text,query){
    const q=searchKey(query);
    return !!q&&(" "+searchKey(text)+" ").indexOf(" "+q+" ")>=0;
  }
  return {spokenToQuery,searchKey,wordsMatch};
});
