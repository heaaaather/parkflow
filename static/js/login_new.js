const container = document.getElementById('container');
const signUpBtn = document.getElementById('signup-btn');
const loginBtn = document.getElementById('login-btn');

signUpBtn.addEventListener('click', () => {
    container.classList.add("active");
});

loginBtn.addEventListener('click', () => {
    container.classList.remove("active");
});
