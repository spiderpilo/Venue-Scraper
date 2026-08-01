//& OBJECTIVE: compare output using raw JavaScript vs. Scrapy.

//& Lazy Dog Target DOM:
// This DOM consists of a "red herring" and the actual content that we
// actually want to extract.
const lazyDogHtml = `
<ul class="sc-dXsUDb">
    <li class="sc-fUuaMo kOihPn">
       <button class="sc-kmiJQj bzKQEm" aria-label="Happy Hour + Late Night" data-uw-rm-empty-ctrl="">
        <span class="sc-TOgAA fKvike">Happy 
            Hour + Late Night
        </span>
       </button> 
    </li>
</ul>
<ul>
    <li class="sc-dXsUDb gSkHhS">
        <button type="button">
            <div class="sc-zlUcK cdFxoN">
                <h4>Happy Hour + Late Night</h4>
                <span>
                    Eats + Sips starting at $3.
                    Hours vary by location.
                </span>
            </div>
        </button>
    </li>
</ul>
`;
//& Yard House DOM:
// Basic testing, easiest to decipher, had no issues in Scrapy.
const yardHouseHtml = `
<section class="happy-hour-section">
    <article class="offer-card">
        <h3>Happy Hour</h3>

        <div class="offer-details">
            <p>Half off select appetizers.</p>
            <p>Monday through Friday from 3 PM to 6 PM.</p>
        </div>
    </article>
</section>
`;

//& DOM Methods:
/*
    document.querySelector("h4");
    document.querySelector("span");
    document.querySelector(".sc-zlUcK");

    .innerHTML
    .textContent
    parentElement.tagName
    parentElement.className
*/

//& Basic Test:
const {JSDOM} = require("jsdom");

const dom = new JSDOM(lazyDogHtml);
const document = dom.window.document;

const heading = document.querySelector("h4");
// console.log(heading.innerHTML); // Testing DOM Methods

//& Conver to Function:
function findPreferredAncestor(node) {
    const preferredTags = new Set([
        "ARTICLE",
        "SECTION",
        "LI",
        "TR",
        "FIGURE"
    ]);

    const maxWords = 180;
    const minWords = 2;

    const normalized = value =>
        (value || "")
            .replace(/\\u00a0/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    
    const wordCount = value =>
        normalized(value)
            .split(/\s+/)
            .filter(Boolean)
            .length;

    const getText = elements => 
        elements 
        ? normalized(elements.innerText ?? elements.textContent) 
        : "";

    let current = node;
    let best = null;

    for(let level = 0; current && level < 7; level += 1) {
        // const text = getText(current);
        const text = getText(current);
        const words = wordCount(text);
        // console.log({
        //     level,
        //     tag: current.tagName,
        //     className: current.className,
        //     words,
        //     text
        // })

        if(words >= minWords && words <= maxWords) {
            best = {
                text,
                words,
                tag: current.tagName,
                class_name:
                    typeof current.className === "string" 
                        ? current.className 
                        : "",
                dom_level: level,
                semantic: preferredTags.has(current.tagName)
            };

            if(best.semantic && words >=5) {
                break;
            }
        }
        current = current.parentElement; 
    }
    return best;
}

//& 1st Test:
const lazyDogHeading_h4 = document.querySelector("h4");
//& 2nd Test: 
const lazyDogHeading_class_select = document.querySelector(".sc-TOgAA");

const result_1 = findPreferredAncestor(lazyDogHeading_h4);
const result_2 = findPreferredAncestor(lazyDogHeading_class_select);

console.log(result_1);
console.log(result_2);