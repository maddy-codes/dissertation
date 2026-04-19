document.addEventListener('DOMContentLoaded', function(event) {
    console.log('DOM fully loaded and parsed');

    var submit_btn = document.getElementById('submit_button');
    
    function title_change() {
        let i = 0;
        const interval = setInterval(() => {
            submit_btn.innerHTML = "Submitting" + ".".repeat(i % 10);
            i++;
        }, 500);
        
        // This line simulates the end of the submit process after 10 seconds.
        setTimeout(() => {
            clearInterval(interval);
            submit_btn.innerHTML = "Submitted";
        }, 10000);
    }
    
    submit_btn.addEventListener('click', title_change);
});
