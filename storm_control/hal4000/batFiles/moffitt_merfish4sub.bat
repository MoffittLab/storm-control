set sc_base=C:\Users\MERFISH5\Code\storm-control\
call C:\Users\MERFISH5\anaconda3\Scripts\activate.bat
call activate merfish4_env
cmd /k python %sc_base%\storm_control\hal4000\hal4000.py %sc_base%\storm_control\hal4000\xml\moffitt_merfish4sub2_config.xml