/*
    TODO: Re-write Yard House candidates function 
    - from arrow function -> actual function.
    - Test with both lazyDogHtml & yardHouseHtml.
    - Make one adjustment to function.
*/

// ======================================
//       LAZY DOG & HARD HOUSE STRINGS
// ======================================
const lazyDogHtml = `
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

// ======================================
//              DOM METHODS
// ======================================
/*
    document.querySelector("h4");
    document.querySelector("span");
    document.querySelector(".sc-zlUcK");

    .innerHTML
    .textContent
    parentElement.tagName
    parentElement.className
*/

// ======================================
//           METHODS TO LOOK INTO 
// ======================================
/* 
    .className
    .tagName
*/

const {JSDOM} = require("jsdom");

const dom = new JSDOM(lazyDogHtml);
const document = dom.window.document;

const heading = document.querySelector("h4");
console.log(heading.innerHTML);

// ======================================
//             ARROW FUNCTIONS 
// ======================================
function normalize(value) {
    return (value || "")
        .replace(/\u00a0/g, " ")
        .replace(/\s+/g, " ")
        .trim();
} 

const wordCount = value => {
    const normalized = normalize(value);

    if(!normalized) {
        return 0;
    }

    return normalized
        .split(/\s+/)
        .filter(Boolean)
        .length;
};

const getText = elements => 
    elements ? normalize(elements.textContent) : "";

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
    console.log("MOW");

    let current = node;
    let best = null;

    for(let level = 0; current && level < 7; level += 1) {
        const text = getText(current);
        const words = wordCount(text);
        console.log({
            level,
            tag: current.tagName,
            className: current.className,
            words,
            text
        })

        if(words >= minWords && words <= maxWords) {
            best = {
                text,
                words,
                tag: current.tagName,
                class_name:
                    typeof current.className === "string" ? current.clsasName : "",
                dom_level: level,
                semantic:
                    preferredTags.has(current.tagName)
            }
        }
        current = current.parentElement; 
    }
    return best;
}

const lazyDogHeading = document.querySelector("h4");

const result = findPreferredAncestor(lazyDogHeading);

console.log(result);