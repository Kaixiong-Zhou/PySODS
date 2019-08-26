import taos
import sys
import random
import numpy
import numpy as np
import pandas as pd
import argparse

from utils.utils import output_performance,insert_data,connect_server,query_data,algorithm_selection


from algo.iForest import iForest

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Anomaly Detection Platform Settings")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--user', default='yli')
    parser.add_argument('--password', default='0906')
    parser.add_argument('--random_seed',default=42, type=int)
    parser.add_argument('--database',default='db')
    parser.add_argument('--table',default='t')
    parser.add_argument('--time_serie',default=False)
    parser.add_argument('--algorithm',default='ocsvm',choices=['iforest','lof','ocsvm'])
    args = parser.parse_args()

    #random seed setting
    rng = np.random.RandomState(args.random_seed)
    np.random.seed(args.random_seed)


    #connection configeration
    conn,cursor=connect_server(args.host, args.user, args.password)

    #read data
    ground_truth=insert_data(conn,cursor,args.database,args.table)
    data = query_data(conn,cursor,args.database,args.table,args.time_serie)

    #algorithm
    clf = algorithm_selection(args.algorithm,random_state=rng)
    clf.fit(data)
    prediction_result = clf.predict(data)

    output_performance(args.algorithm,ground_truth,prediction_result)


    conn.close()