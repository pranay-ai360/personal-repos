/**
 * 1. open cloudflare dashboard, choose domain, go to DNS section
 * 2. open browser's dev tool (via F12 or inspect or however)
 * 3. in devtool, go to console tab
 * 4. clear all existing messages
 * 5. paste all script below
 * 6. hit enter and watch
 * 7. script only delete records displayed in the screen
 * 8. if want to delete more, refresh browser and run script again
 * 
 * credit: edited from https://gist.github.com/AidasK/9550e1eb97b3b121c5122aef0d778608
 */

deleteAllRecords();

async function deleteAllRecords() {
    let e;
    filterEditButtons().forEach((e) => e.click());
    while (e = filterDeleteButtons()[0]) {
        e.click();
        await confirmDelete();
    }
}
function filterDeleteButtons() {
    return [
        ...[...document.querySelectorAll('a')].filter((e) => e.innerHTML === '<span>Delete</span>'),
        ...[...document.querySelectorAll('button')].filter((e) => e.innerHTML === 'Delete'),
    ];
}
function filterEditButtons() {
    return [
        ...document.querySelectorAll('a'),//old layout
        ...document.querySelectorAll('button')
    ].filter((e) => e.innerHTML.includes('<span>Edit</span>'));
}
function confirmDelete(iteration) {
    iteration = iteration || 1;
    return new Promise((resolve, reject) => {
        setTimeout(async () => {
            let button = [...document.querySelectorAll('button')].filter((e) => e.innerHTML === '<span>Delete</span>')[0];
            if (button) {
                button.click();
                await waitConfirmDelete();
                resolve();
            } else if (iteration > 30) {
                console.log('failed confirmDelete');
                reject();
            } else {
                confirmDelete(iteration + 1)
            }
        }, 100);
    });
}
function waitConfirmDelete() {
    return new Promise((resolve, reject) => {
        let iteration = 1;
        let i = setInterval(() => {
            if (iteration++ > 30) {
                clearInterval(i);
                reject();
                return;
            }
            if ([...document.querySelectorAll('button')].filter((e) => e.innerHTML === '<span>Delete</span>')[0]) {
                return;
            }
            clearInterval(i);
            resolve();
        }, 100)
    });
}