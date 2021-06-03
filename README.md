# work assistant

telegram bot for simplifying some work processes


## preparing to run

just copy source into some directory, change to that directory by `cd <my_dir>` and run `re-run-bot.sh`.



## run as a service

(for instructions thanks to 
[Dr. Shubham Dipt and his article](https://www.shubhamdipt.com/blog/how-to-create-a-systemd-service-in-linux/))

- create `work_assistant_bot.service` in `/etc/systemd/system` with following content
(don't forget replace `<work_dorectory>` to working directory of your bot instance):
    ```service
    [Unit]
    Description=Telegram bot to assist you in work processes (https://github.com/atronah/work_assistant)
    
    [Service]
    User=atronah
    WorkingDirectory=<work_dorectory>
    ExecStart=/bin/bash -c 'cd <work_dorectory>/ && source venv/bin/activate && <work_dorectory>/bot.py'
    Restart=always
    
    [Install]
    WantedBy=multi-user.target
    ```
- reload services by command `sudo systemctl daemon-reload`
- start service by command `sudo systemctl start work_assistant_bot`
- check status by command `sudo systemctl start work_assistant_bot`
- stop service by command `sudo systemctl stop work_assistant_bot`
- enable service on every reboot `sudo systemctl enable work_assistant_bot`